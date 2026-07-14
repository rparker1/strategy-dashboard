"""Generates a phone-friendly, self-contained HTML dashboard from engine state."""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
OUT = os.path.join(HERE, "dashboard.html")

NAMES = {
    "S1": "SMA 20/50 Trend", "S2": "RSI(2) Reversion", "S3": "Bollinger Reversion",
    "S4": "Donchian Breakout", "S5": "MACD Momentum", "S6": "90d Momentum",
    "S7": "Vol-Target Trend", "S8": "Keltner Squeeze", "S9": "3-Down Pullback",
    "S10": "Buy & Hold (control)", "P1": "X-Sect Momentum Top-2", "P2": "Inverse-Vol Parity",
    "P3": "Dual Momentum", "P4": "ETH/BTC Rel Value", "P5": "AAPL/MSFT Pairs",
    "P6": "Crypto-Equity Rotation", "P7": "Ensemble Voter", "P8": "Min-Variance",
    "P9": "Seasonality Hybrid", "P10": "Regime Switcher",
}


def build(state, prices, flags):
    cap = CFG["sleeve_capital"]
    rows, total = [], 0.0
    for sid in CFG["sleeves"]:
        sv = state["sleeves"][sid]
        eq = sv["cash"] + sum(q * prices.get(s, 0) for s, q in sv["positions"].items())
        total += eq
        ret = eq / cap - 1
        dd = 1 - eq / max(sv["peak"], 1e-9)
        pos = ", ".join(f"{s.replace('/USD','')}{'−' if q<0 else ''}" for s, q in
                        sorted(sv["positions"].items(), key=lambda kv: -abs(kv[1] * prices.get(kv[0], 0))))
        status = "⚠️ FLAT" if sv["flattened"] else ("—" if not sv["positions"] else pos)
        cls = "pos" if ret >= 0 else "neg"
        rows.append(f"<tr><td><b>{sid}</b><br><span class='sub'>{NAMES[sid]}</span></td>"
                    f"<td class='{cls}'>{ret:+.2%}<br><span class='sub'>${eq:,.0f}</span></td>"
                    f"<td>{dd:.1%}</td><td class='sub'>{status}</td></tr>")
    tret = total / (cap * len(CFG["sleeves"])) - 1
    flag_html = "".join(f"<div class='flag'>{f}</div>" for f in flags) or \
                "<div class='ok'>No flags — all sleeves within risk limits.</div>"
    # recent journal
    recent = []
    jp = os.path.join(HERE, "state", "journal.jsonl")
    if os.path.exists(jp):
        lines = open(jp).read().strip().splitlines()[-3:]
        for ln in reversed(lines):
            j = json.loads(ln)
            if j.get("type") == "run":
                fees = sum(d.get("fee", 0) for d in j.get("decisions", []))
                recent.append(f"<div class='sub'>{j['ts'][:16]}Z · {len(j.get('decisions', []))} fills, "
                              f"${fees:.2f} fees{' · DRY' if j.get('dry') else ''}</div>")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f1115">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>if('serviceWorker' in navigator){{navigator.serviceWorker.register('sw.js');}}</script>
<title>Strategy Test Dashboard</title><style>
body{{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#0f1115;color:#e8eaed;padding:12px}}
h1{{font-size:1.15rem;margin:4px 0}} .hero{{font-size:1.9rem;font-weight:700;margin:2px 0}}
.sub{{color:#9aa0a6;font-size:.78rem}} .pos{{color:#4ade80}} .neg{{color:#f87171}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
td{{padding:8px 6px;border-bottom:1px solid #23262d;font-size:.85rem;vertical-align:top}}
.flag{{background:#452020;border-left:3px solid #f87171;padding:8px;margin:6px 0;border-radius:4px;font-size:.85rem}}
.ok{{background:#15251a;border-left:3px solid #4ade80;padding:8px;margin:6px 0;border-radius:4px;font-size:.85rem}}
</style></head><body>
<h1>Strategy Test — Simulated $100k</h1>
<div class="hero {'pos' if tret>=0 else 'neg'}">{tret:+.2%}</div>
<div class="sub">Total ${total:,.0f} across 20 sleeves · updated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z</div>
{flag_html}
<table><tr class="sub"><td>Sleeve</td><td>Return</td><td>DD</td><td>Holding</td></tr>
{''.join(rows)}</table>
<h1 style="margin-top:14px">Recent runs</h1>{''.join(recent)}
</body></html>"""
    with open(OUT, "w") as f:
        f.write(html)
    pub = os.path.join(HERE, "docs")
    if os.path.isdir(pub):  # mirror into the PWA publish dir if it exists
        with open(os.path.join(pub, "index.html"), "w") as f:
            f.write(html)
    return OUT
