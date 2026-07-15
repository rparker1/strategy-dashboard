"""Backtest the EXACT frozen strategy rules over the stored price history.

Purpose (see EVALUATION.md): give every sleeve a ~1.5-2 year simulated track
record so the live quarter's job becomes "verify live behavior matches the
backtest," not "measure the edge from 63 days" (impossible).

Method: daily steps. On each date t, each sleeve sees bars up to and including
t and trades at t's close with the same fee haircut as live (5bps stocks,
25bps crypto). This approximates the live evening run. Differences vs live:
one decision/day instead of two, and fills at the daily close instead of an
intraday quote. Both are noted in the evaluation, not hidden.

    python backtest.py            # full run -> state/backtest.json
    python backtest.py --quick    # last 120 days only (smoke test)
"""
import datetime as dt
import json
import os
import sys
import time

import pandas as pd

import datastore
import strategies

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
ALL = CFG["stock_symbols"] + CFG["crypto_symbols"]
CRYPTO = set(CFG["crypto_symbols"])
OUT = os.path.join(HERE, "state", "backtest.json")
WARMUP = 265  # bars needed before a symbol's signals are trusted (SMA200 + slack)


def run(quick=False):
    bars_full = datastore.load_bars()
    for s in ALL:
        assert s in bars_full and len(bars_full[s]) >= WARMUP + 30, f"insufficient history for {s}"
    # trading calendar: crypto trades every day; stocks simply hold on weekends
    cal = bars_full["BTC/USD"].index
    start_dates = [bars_full[s].index[WARMUP] for s in ALL]
    start = max(start_dates)
    dates = cal[cal >= start]
    if quick:
        dates = dates[-120:]

    cap = CFG["sleeve_capital"]
    sleeves = {sid: {"cash": cap, "positions": {}, "peak": cap, "memo": {},
                     "flattened": False, "ever_traded": False}
               for sid in CFG["sleeves"]}
    equity_series = {sid: [] for sid in CFG["sleeves"]}
    trade_counts = {sid: 0 for sid in CFG["sleeves"]}
    fee_paid = {sid: 0.0 for sid in CFG["sleeves"]}
    t0 = time.time()

    for i, d in enumerate(dates):
        bars = {s: df.loc[:d] for s, df in bars_full.items()}
        prices = {s: float(bars[s]["close"].iloc[-1]) for s in ALL}
        now = dt.datetime(d.year, d.month, d.day, 21, 0)  # evening-run equivalent
        for sid, sv in sleeves.items():
            eq = sv["cash"] + sum(q * prices[s] for s, q in sv["positions"].items())
            sv["peak"] = max(sv["peak"], eq)
            if sv["flattened"] or 1 - eq / sv["peak"] > CFG["sleeve_max_drawdown"]:
                # live rule: freeze on 15% DD. In backtest we auto-unfreeze after
                # 5 days flat (the runbook's default review outcome) to keep the
                # series informative; freezes are counted.
                if not sv["flattened"]:
                    sv["flattened"] = True
                    sv["memo"]["_frozen_on"] = str(d.date())
                    sv["memo"]["_freezes"] = sv["memo"].get("_freezes", 0) + 1
                elif (pd.Timestamp(d) - pd.Timestamp(sv["memo"]["_frozen_on"])).days >= 5:
                    sv["flattened"] = False
                    sv["peak"] = eq  # reset peak on re-entry, matching a fresh review
            targets = ({s: 0.0 for s in ALL} if sv["flattened"] else None)
            if targets is None:
                try:
                    targets = strategies.REGISTRY[sid](bars, sv, now)
                except Exception:
                    targets = None
            if targets is not None:
                gross = sum(abs(w) for w in targets.values())
                if gross > 1.5:
                    targets = {s: w * 1.5 / gross for s, w in targets.items()}
                for s, w in targets.items():
                    if s in CRYPTO and w < 0:
                        w = 0.0
                    cur = sv["positions"].get(s, 0.0)
                    des = w * eq / prices[s]
                    delta = des - cur
                    notional = abs(delta) * prices[s]
                    if notional < max(CFG["min_trade_notional"], 0.01 * eq):
                        continue
                    fee = notional * (CFG["fee_bps_crypto"] if s in CRYPTO
                                      else CFG["fee_bps_stock"]) / 10000.0
                    sv["positions"][s] = des
                    sv["cash"] -= delta * prices[s] + fee
                    sv["ever_traded"] = True
                    trade_counts[sid] += 1
                    fee_paid[sid] += fee
                sv["positions"] = {s: q for s, q in sv["positions"].items() if abs(q) > 1e-9}
            eq = sv["cash"] + sum(q * prices[s] for s, q in sv["positions"].items())
            equity_series[sid].append(round(eq, 2))
        if i % 50 == 0:
            print(f"{i}/{len(dates)} {d.date()} ({time.time()-t0:.0f}s)", flush=True)

    result = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dates": [str(d.date()) for d in dates],
        "note": "daily steps, close fills, same fee haircut as live; freeze rule auto-reviews after 5d",
        "equity": equity_series,
        "trades": trade_counts,
        "fees": {k: round(v, 2) for k, v in fee_paid.items()},
        "freezes": {sid: sleeves[sid]["memo"].get("_freezes", 0) for sid in sleeves},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w"))
    print(f"\nwrote {OUT}: {len(dates)} days, {time.time()-t0:.0f}s")
    return result


if __name__ == "__main__":
    run(quick="--quick" in sys.argv)
