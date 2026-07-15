"""Day-90 evaluation — applies the PRE-REGISTERED criteria in EVALUATION.md.

Run AFTER regenerating the backtest the same day (`python backtest.py`), so the
backtest window covers the live quarter and the consistency check has
overlapping dates.

    python evaluate.py            # writes state/evaluation_report.md + .json

The thresholds live in EVALUATION.md and are frozen. This code may be bug-fixed;
the criteria may not be moved after results exist.
"""
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
CAP = CFG["sleeve_capital"]

# ---- frozen thresholds (mirror EVALUATION.md; that document is authoritative)
TH = {
    "fee_drag_kill": 0.03,        # annualized fees/capital above this = operational kill
    "consistency_min": 0.60,      # live-vs-backtest daily return correlation below this = defect
    "redundancy_corr": 0.90,      # backtest daily return corr above this = redundant pair
    "redundancy_live_confirm": 0.80,
    "min_live_days": 60,          # evaluation invalid before this many live trading days
    "family_tilt_cap": 0.20,      # max capital tilt between families, regardless of results
}
FAMILIES = {
    "trend": ["S1", "S4", "S5", "S6", "S7", "S8"],
    "reversion": ["S2", "S3", "S9"],
    "benchmark": ["S10"],
    "allocation": ["P1", "P2", "P3", "P6", "P8"],
    "relative_value": ["P4", "P5"],
    "meta": ["P7", "P9", "P10"],
}


def daily_returns_from_history(hist):
    """hist: [[iso_ts, equity], ...] possibly 2+/day -> daily pct returns Series."""
    if len(hist) < 3:
        return pd.Series(dtype=float)
    s = pd.Series([h[1] for h in hist],
                  index=pd.to_datetime([h[0] for h in hist]))
    daily = s.resample("D").last().dropna()
    return daily.pct_change().dropna()


def sharpe(r, periods=365):
    if len(r) < 10 or r.std() == 0:
        return np.nan
    return float(r.mean() / r.std() * np.sqrt(periods))


def block_bootstrap_ci(r, stat=sharpe, n=2000, block=5, alpha=0.05, seed=7):
    """Circular block bootstrap CI for a return-series statistic."""
    r = np.asarray(r, dtype=float)
    if len(r) < 20:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    T = len(r)
    stats = []
    for _ in range(n):
        idx = []
        while len(idx) < T:
            s0 = rng.integers(0, T)
            idx.extend([(s0 + k) % T for k in range(block)])
        stats.append(stat(pd.Series(r[np.array(idx[:T])])))
    lo, hi = np.nanpercentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def main():
    state = json.load(open(os.path.join(HERE, "state", "state.json")))
    bt = json.load(open(os.path.join(HERE, "state", "backtest.json")))
    bt_dates = pd.to_datetime(bt["dates"])
    bt_eq = {sid: pd.Series(v, index=bt_dates) for sid, v in bt["equity"].items()}
    bt_ret = {sid: s.pct_change().dropna() for sid, s in bt_eq.items()}
    bt_window_days = (bt_dates[-1] - bt_dates[0]).days

    live_ret, live_stats = {}, {}
    fills = {}
    jp = os.path.join(HERE, "state", "journal.jsonl")
    for ln in open(jp):
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        if j.get("type") == "run" and not j.get("dry"):
            for d in j.get("decisions", []):
                fills.setdefault(d["sleeve"], []).append(abs(d["notional"]))

    rows, verdicts = {}, {}
    for sid, sv in state["sleeves"].items():
        r = daily_returns_from_history(sv["history"])
        live_ret[sid] = r
        live_days = len(r)
        eq_now = sv["history"][-1][1] if sv["history"] else CAP
        ann_frac = max(live_days, 1) / 365
        fees_live = 0.0  # per-sleeve live fees from journal
        turnover = sum(fills.get(sid, [])) / CAP
        # fees approximated from fills at the sleeve's mixed rate is imprecise;
        # use backtest fee rate per trade as cross-check instead.
        sh_live = sharpe(r)
        ci = block_bootstrap_ci(r) if live_days >= 20 else (np.nan, np.nan)
        # consistency: correlation of live vs backtest daily returns on shared dates
        common = r.index.intersection(bt_ret[sid].index)
        consistency = (float(r.loc[common].corr(bt_ret[sid].loc[common]))
                       if len(common) >= 30 else np.nan)
        fee_drag_bt = bt["fees"][sid] / CAP / (bt_window_days / 365)
        rows[sid] = {
            "live_days": live_days,
            "live_return": eq_now / CAP - 1,
            "live_sharpe": sh_live, "live_sharpe_ci": ci,
            "live_turnover_x": turnover,
            "bt_return": float(bt_eq[sid].iloc[-1] / bt_eq[sid].iloc[0] - 1),
            "bt_sharpe": sharpe(bt_ret[sid]),
            "bt_maxdd": float((1 - bt_eq[sid] / bt_eq[sid].cummax()).max()),
            "bt_fee_drag_ann": fee_drag_bt,
            "bt_freezes": bt["freezes"].get(sid, 0),
            "consistency_corr": consistency,
        }

    # redundancy pairs (backtest corr, live-confirmed where possible)
    bt_ret_df = pd.DataFrame(bt_ret).dropna()
    corr = bt_ret_df.corr()
    redundant = []
    sids = list(corr.columns)
    for i, a in enumerate(sids):
        for b in sids[i + 1:]:
            if corr.loc[a, b] > TH["redundancy_corr"]:
                lc = np.nan
                ca = live_ret[a].index.intersection(live_ret[b].index)
                if len(ca) >= 30:
                    lc = float(live_ret[a].loc[ca].corr(live_ret[b].loc[ca]))
                confirmed = (np.isnan(lc)) or (lc > TH["redundancy_live_confirm"])
                redundant.append({"pair": [a, b], "bt_corr": float(corr.loc[a, b]),
                                  "live_corr": lc, "confirmed": bool(confirmed)})

    # verdicts per frozen criteria
    enough = all(v["live_days"] >= TH["min_live_days"] for v in rows.values())
    for sid, v in rows.items():
        reasons = []
        if v["bt_fee_drag_ann"] > TH["fee_drag_kill"]:
            reasons.append(f"KILL-COST: fee drag {v['bt_fee_drag_ann']:.1%}/yr > {TH['fee_drag_kill']:.0%}")
        if not np.isnan(v["consistency_corr"]) and v["consistency_corr"] < TH["consistency_min"]:
            reasons.append(f"DEFECT: live/backtest corr {v['consistency_corr']:.2f} < {TH['consistency_min']}")
        for rpair in redundant:
            if sid in rpair["pair"] and rpair["confirmed"]:
                other = [x for x in rpair["pair"] if x != sid][0]
                if rows[other]["live_turnover_x"] < v["live_turnover_x"]:
                    reasons.append(f"KILL-REDUNDANT: >{TH['redundancy_corr']:.0%} corr with {other}, which trades less")
        verdicts[sid] = {"verdict": ("KILL" if any(x.startswith("KILL") for x in reasons)
                                     else "REVIEW-DEFECT" if reasons else "CONTINUE"),
                         "reasons": reasons}

    # family pooling (equal-weighted mean of member daily returns, live)
    fam = {}
    for name, members in FAMILIES.items():
        rr = pd.DataFrame({m: live_ret[m] for m in members if len(live_ret[m])}).dropna()
        fam[name] = {"live_sharpe": sharpe(rr.mean(axis=1)) if len(rr) >= 20 else np.nan,
                     "bt_sharpe": sharpe(pd.DataFrame({m: bt_ret[m] for m in members}).dropna().mean(axis=1))}

    report = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "valid": bool(enough),
        "validity_note": ("OK" if enough else
                          f"INVALID for final decisions: fewer than {TH['min_live_days']} live days. "
                          "Interim diagnostics only."),
        "thresholds": TH, "sleeves": rows, "verdicts": verdicts,
        "redundant_pairs": redundant, "families": fam,
    }
    json.dump(report, open(os.path.join(HERE, "state", "evaluation_report.json"), "w"),
              indent=1, default=str)

    lines = [f"# Evaluation report — {report['generated'][:16]}Z",
             f"\n**Validity: {report['validity_note']}**\n",
             "| sleeve | live ret | live Sharpe [95% CI] | consist. | fee drag/yr | verdict |",
             "|---|---|---|---|---|---|"]
    for sid, v in rows.items():
        ci = v["live_sharpe_ci"]
        cis = f"[{ci[0]:.1f}, {ci[1]:.1f}]" if not np.isnan(ci[0]) else "n/a"
        lines.append(f"| {sid} | {v['live_return']:+.2%} | {v['live_sharpe'] if not np.isnan(v['live_sharpe']) else float('nan'):.2f} {cis} "
                     f"| {v['consistency_corr'] if not np.isnan(v['consistency_corr']) else float('nan'):.2f} "
                     f"| {v['bt_fee_drag_ann']:.1%} | **{verdicts[sid]['verdict']}** |")
    lines.append("\n## Verdict reasons\n")
    for sid, vv in verdicts.items():
        if vv["reasons"]:
            lines.append(f"- **{sid}**: " + "; ".join(vv["reasons"]))
    lines.append("\n## Redundant pairs (backtest corr > 0.90)\n")
    for rp in redundant:
        lines.append(f"- {rp['pair'][0]}/{rp['pair'][1]}: bt {rp['bt_corr']:.2f}, live {rp['live_corr']}")
    lines.append("\n## Families (pooled)\n")
    for name, f in fam.items():
        lines.append(f"- {name}: live Sharpe {f['live_sharpe']}, backtest Sharpe {f['bt_sharpe']:.2f}")
    with open(os.path.join(HERE, "state", "evaluation_report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))
    print(f"\nwrote state/evaluation_report.md and .json")


if __name__ == "__main__":
    main()
