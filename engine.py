"""Simulator engine: runs all 20 sleeves against file-based market data,
fills at latest fetched price MINUS a slippage+fee haircut, journals every
decision, and regenerates the dashboard. No broker; the ledger is the account.

Usage:
    python engine.py run          # full run (simulated fills)
    python engine.py run --dry    # compute + journal decisions, no fills
    python engine.py status       # quick sleeve summary
"""
import datetime as dt
import json
import os
import sys

import datastore
import strategies

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
STATE_PATH = os.path.join(HERE, "state", "state.json")
JOURNAL_PATH = os.path.join(HERE, "state", "journal.jsonl")
ALL = CFG["stock_symbols"] + CFG["crypto_symbols"]
CRYPTO = set(CFG["crypto_symbols"])


def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    cap = CFG["sleeve_capital"]
    return {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account_peak": cap * len(CFG["sleeves"]),
        "killed": False,
        "fees_paid": 0.0,
        "sleeves": {sid: {"cash": cap, "positions": {}, "peak": cap, "memo": {},
                          "flattened": False, "ever_traded": False, "history": []}
                    for sid in CFG["sleeves"]},
    }


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    json.dump(state, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, STATE_PATH)


def journal(entry):
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    entry["ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def sleeve_equity(sleeve, prices):
    return sleeve["cash"] + sum(q * prices.get(s, 0.0)
                                for s, q in sleeve["positions"].items())


def run(dry=False):
    now = dt.datetime.now(dt.timezone.utc)
    state = load_state()
    bars = datastore.load_bars()
    prices, quote_ts = datastore.latest_prices()

    missing = [s for s in ALL if s not in prices or s not in bars
               or bars[s].empty or len(bars[s]) < 100]
    if missing:
        journal({"type": "error", "msg": f"insufficient data for {missing}, aborting"})
        return {"error": f"insufficient data: {missing}"}
    stale = [s for s in ALL
             if (dt.datetime.now() - bars[s].index[-1].to_pydatetime()).days > 5]
    flags = [f"STALE HISTORY (>5d): {stale} — ingest new bars before trusting signals"] if stale else []

    total_equity = sum(sleeve_equity(sv, prices) for sv in state["sleeves"].values())
    state["account_peak"] = max(state["account_peak"], total_equity)
    account_dd = 1 - total_equity / state["account_peak"]
    decisions = []

    if account_dd > CFG["account_max_drawdown"] and not state["killed"]:
        state["killed"] = True
        flags.append(f"ACCOUNT KILL SWITCH: drawdown {account_dd:.1%} — flattening everything")

    for sid in CFG["sleeves"]:
        sv = state["sleeves"][sid]
        eq = sleeve_equity(sv, prices)
        sv["peak"] = max(sv["peak"], eq)
        dd = 1 - eq / sv["peak"]

        if state["killed"] or sv["flattened"]:
            targets = {s: 0.0 for s in ALL}
        elif dd > CFG["sleeve_max_drawdown"]:
            sv["flattened"] = True
            flags.append(f"{sid}: sleeve drawdown {dd:.1%} > 15% — flattened, needs review")
            targets = {s: 0.0 for s in ALL}
        else:
            try:
                targets = strategies.REGISTRY[sid](bars, sv, now)
            except Exception as e:
                flags.append(f"{sid}: strategy error {e!r} — holding position")
                targets = None
        if targets is None:
            sv["history"].append([now.isoformat(), round(eq, 2)])
            continue

        gross = sum(abs(w) for w in targets.values())
        if gross > 1.5:  # rule 2: cap gross exposure
            targets = {s: w * 1.5 / gross for s, w in targets.items()}

        for s, w in targets.items():
            if s in CRYPTO and w < 0:
                w = 0.0  # no crypto shorts
            cur_q = sv["positions"].get(s, 0.0)
            des_q = w * eq / prices[s]
            delta = des_q - cur_q
            notional = abs(delta) * prices[s]
            if notional < max(CFG["min_trade_notional"], 0.01 * eq):
                continue
            fee = notional * (CFG["fee_bps_crypto"] if s in CRYPTO
                              else CFG["fee_bps_stock"]) / 10000.0
            if not dry:
                sv["positions"][s] = des_q
                sv["cash"] -= delta * prices[s] + fee
                sv["ever_traded"] = True
                state["fees_paid"] += fee
            decisions.append({"sleeve": sid, "symbol": s, "delta_qty": round(delta, 8),
                              "notional": round(delta * prices[s], 2),
                              "fee": round(fee, 4), "target_w": round(w, 4)})
        sv["positions"] = {s: q for s, q in sv["positions"].items() if abs(q) > 1e-9}
        sv["history"].append([now.isoformat(), round(sleeve_equity(sv, prices), 2)])

    if not dry:
        save_state(state)
    journal({"type": "run", "dry": dry, "total_equity": round(total_equity, 2),
             "account_dd": round(account_dd, 4), "quote_ts": quote_ts,
             "decisions": decisions, "flags": flags})
    try:
        import dashboard
        dashboard.build(state, prices, flags)
    except Exception as e:
        journal({"type": "error", "msg": f"dashboard build failed: {e!r}"})
    return {"total_equity": round(total_equity, 2), "decisions": len(decisions),
            "fees_paid_total": round(state["fees_paid"], 2), "flags": flags}


def status():
    state = load_state()
    prices, ts = datastore.latest_prices()
    total = 0.0
    for sid, sv in state["sleeves"].items():
        eq = sleeve_equity(sv, prices)
        total += eq
        print(f"{sid:>4}: ${eq:8,.2f}  ret {(eq / CFG['sleeve_capital'] - 1):+7.2%}"
              f"  {'FLAT' if sv['flattened'] else ''}")
    print(f"TOTAL ${total:,.2f} | fees ${state['fees_paid']:,.2f} | quotes {ts}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        print(json.dumps(run(dry="--dry" in sys.argv), indent=2))
    elif cmd == "status":
        status()
    elif cmd == "note":
        # strategic decision / review by the check-in session, shown in the PWA:
        #   python engine.py note review "Weekly review: ..."
        #   python engine.py note decision "Re-enabled S4 after 5 days flat because ..."
        journal({"type": "note", "kind": sys.argv[2], "text": sys.argv[3]})
        print("noted")
