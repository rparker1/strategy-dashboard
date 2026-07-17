"""Full-report PWA dashboard: hero equity, account curve, exposure, per-sleeve
cards (strategy description, positions, sparkline), activity feed, methodology.
Self-contained HTML + inline SVG, no external libraries. Dark, mobile-first.

Palette per the dataviz reference (dark mode steps): series blue #3987e5,
long/short diverging blue/red, status colors reserved for flags, text tokens
for all text (marks carry color, text does not).
"""
import datetime as dt
import html as html_mod
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
OUT = os.path.join(HERE, "dashboard.html")

SURFACE = "#16171c"
PAGE = "#0f1115"

META = {  # id: (name, what it does, honest weakness)
 "S1": ("SMA 20/50 Trend", "Long when the 20-day average crosses above the 50-day; flat on the reverse cross. Classic trend capture on every symbol.", "Whipsaws in ranging markets — death by a thousand cuts in chop."),
 "S2": ("RSI(2) Reversion", "Buys extreme short-term oversold dips (RSI2<10) but only in uptrends (price above 200-day avg); exits on RSI2>70 or after 5 days.", "Catches falling knives when the regime breaks; the trend filter lags."),
 "S3": ("Bollinger Reversion", "Buys closes below the lower Bollinger band; exits at the 20-day average. Stop at 2 ATR below entry.", "In strong downtrends price walks the band — the stop does all the risk work."),
 "S4": ("Donchian Breakout", "Turtle-style: buys 20-day-high breakouts, exits on 10-day lows.", "Low win rate by design; needs a big trend to pay for many small losses."),
 "S5": ("MACD Momentum", "Long when MACD crosses above its signal line with rising histogram; flat on the down-cross.", "Heavily correlated with S1 — kept to test whether the faster variant adds anything."),
 "S6": ("90d Momentum", "Long any symbol whose 90-day return is positive; flat otherwise. The most robust effect in the academic literature.", "Very slow — may trade twice in the whole test. Judge positioning, not activity."),
 "S7": ("Vol-Target Trend", "Same signal as S6, but position size scales down when 20-day volatility exceeds a 10% annualized target.", "A controlled experiment vs S6, not a new signal; sizing is coarse at this scale."),
 "S8": ("Keltner Squeeze", "Waits for volatility compression (Bollinger inside Keltner), buys the upside break; exits below the 10-day EMA.", "Squeezes resolve both ways; long-only eats the downside breaks as losses."),
 "S9": ("3-Down Pullback", "Buys 3 consecutive down-closes in an uptrend; exits on the first up-close or after 7 days.", "Similar exposure to S2 — tests whether dumb-simple matches RSI's cleverness."),
 "S10": ("Buy & Hold (control)", "Equal weight across all 7 symbols, continuously rebalanced. The benchmark every other sleeve must beat.", "None — that's the point. If the clever sleeves can't beat this, that's the finding."),
 "P1": ("X-Sect Momentum Top-2", "Ranks all 7 symbols by 30-day return, holds the top 2. A 2% hysteresis buffer reduces churn at rank boundaries.", "High turnover when ranks are close; the buffer helps but doesn't eliminate it."),
 "P2": ("Inverse-Vol Parity", "Weights every symbol by the inverse of its volatility, rebalanced weekly. Crypto gets small weights — deliberately.", "Naive risk balancing; tests whether it beats plain equal weight (S10)."),
 "P3": ("Dual Momentum", "Each week holds the single best 90-day performer — or 100% cash if even the best is negative.", "Maximum concentration: one asset at a time, lumpy equity curve."),
 "P4": ("ETH/BTC Rel Value", "Tilts between ETH and BTC when their ratio stretches >1.5 standard deviations from its 60-day mean.", "Long-only tilting (no crypto shorts here) mutes the edge substantially."),
 "P5": ("AAPL/MSFT Pairs", "Shorts the rich leg and buys the cheap leg when the hedged spread stretches past 2 standard deviations; exits near zero.", "Co-moving megacaps can stay dislocated on idiosyncratic news far longer than the stats suggest."),
 "P6": ("Crypto-Equity Rotation", "Weekly winner-takes-all between the crypto basket, SPY, and cash, by 30-day return.", "Whipsaw risk at regime turns; one bad rotation can cost a month of edge."),
 "P7": ("Ensemble Voter", "For each symbol, exposure is proportional to how many of S1–S9's signals are currently long it. Trades the combination of everything.", "If the ensemble can't beat its average member, the 9 signals are the same trade in different clothes — a useful finding either way."),
 "P8": ("Min-Variance", "Long-only minimum-variance weights from a rolling 60-day covariance matrix, capped at 40% per asset, weekly.", "Covariance from 60 observations on 7 assets is noisy; expect unstable weights."),
 "P9": ("Seasonality Hybrid", "Long BTC+ETH over weekends; long SPY at the turn of each month. Flat otherwise.", "Calendar effects are the most likely to be arbitraged away — the sleeve most expected to fail, included as a falsifiable test."),
 "P10": ("Regime Switcher", "Allocates to trend signals (S1/S4/S6) when SPY is above its 200-day average with calm vol; to half-size mean-reversion (S2/S3/S9) otherwise.", "Tests the allocator's real job: matching signal type to regime. Regime flips lag by construction."),
}


def esc(s):
    return html_mod.escape(str(s))


def money(x):
    return f"${x:,.0f}"


def sleeve_equity(sv, prices):
    return sv["cash"] + sum(q * prices.get(s, 0.0) for s, q in sv["positions"].items())



MODAL = """
<style>
#eqmodal{position:fixed;inset:0;z-index:30;background:#0f1115;display:none;flex-direction:column;padding:14px;padding-top:calc(14px + env(safe-area-inset-top));padding-bottom:calc(14px + env(safe-area-inset-bottom))}
#eqmodal.open{display:flex;animation:tabin .3s cubic-bezier(.2,.7,.3,1)}
.mhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.mtitle{font-family:var(--disp);font-weight:700;font-size:1.05rem}
.mclose{background:#16171c;border:1px solid rgba(255,255,255,.1);border-radius:10px;color:#c3c2b7;width:38px;height:38px;font-size:1.1rem;display:flex;align-items:center;justify-content:center;cursor:pointer}
.ranges{display:flex;gap:6px;margin-bottom:10px}
.ranges button{flex:1;background:#16171c;border:1px solid rgba(255,255,255,.08);border-radius:8px;color:#898781;padding:7px 0;font-size:.78rem;font-family:var(--disp);font-weight:600;cursor:pointer}
.ranges button.sel{background:#1d2a45;border-color:#3987e5;color:#6da7ec}
.mstats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.mstat{background:#16171c;border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:7px 8px}
.mstat .l{color:#898781;font-size:.62rem;letter-spacing:.04em;text-transform:uppercase}
.mstat .v{font-family:var(--disp);font-weight:600;font-size:.88rem;margin-top:1px}
#mchartwrap{flex:1;position:relative;background:#16171c;border:1px solid rgba(255,255,255,.07);border-radius:12px;overflow:hidden;touch-action:none;min-height:200px}
#mtip{position:absolute;pointer-events:none;background:rgba(15,17,21,.95);border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:7px 9px;font-size:.75rem;display:none;z-index:2;min-width:130px;backdrop-filter:blur(6px)}
#mtip .tt{color:#898781;font-size:.68rem;margin-bottom:3px}
#mtip .row{display:flex;align-items:center;gap:6px;margin:2px 0}
#mtip .key{display:inline-block;width:12px;height:2px;border-radius:1px}
#mtip .val{font-family:var(--disp);font-weight:600}
#mtip .nm{color:#898781;font-size:.68rem}
.mlegend{display:flex;gap:14px;margin-top:8px;font-size:.72rem;color:#c3c2b7;align-items:center}
.mlegend .key{display:inline-block;width:14px;height:2px;border-radius:1px;margin-right:5px;vertical-align:3px}
</style>
<div id="eqmodal" role="dialog" aria-label="Interactive account equity chart">
<div class="mhead"><span class="mtitle">Account equity</span>
<button class="mclose" id="mclose" aria-label="Close">&#10005;</button></div>
<div class="ranges" id="mranges">
<button data-r="86400">24H</button><button data-r="604800">7D</button>
<button data-r="2592000">30D</button><button data-r="0" class="sel">ALL</button>
</div>
<div class="mstats">
<div class="mstat"><div class="l">Return</div><div class="v" id="ms-ret">&ndash;</div></div>
<div class="mstat"><div class="l">High</div><div class="v" id="ms-hi">&ndash;</div></div>
<div class="mstat"><div class="l">Low</div><div class="v" id="ms-lo">&ndash;</div></div>
<div class="mstat"><div class="l">Max DD</div><div class="v" id="ms-dd">&ndash;</div></div>
</div>
<div id="mchartwrap"><div id="mtip"></div></div>
<div class="mlegend">
<span><span class="key" style="background:#3987e5"></span>Account</span>
<span><span class="key" style="background:#6a6c72"></span>Buy &amp; hold control (rebased)</span>
<span style="margin-left:auto" class="sub" id="mcount"></span>
</div>
</div>
<script>
(function() {
  var D = __DATA__;
  var modal = document.getElementById("eqmodal"), wrap = document.getElementById("mchartwrap");
  var tip = document.getElementById("mtip");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var rangeSec = 0, view = null;

  function usd(v) { return "$" + Math.round(v).toLocaleString(); }
  function pct(v) { return (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(2) + "%"; }
  function fdate(ts) {
    var d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, {day: "numeric", month: "short"}) + " " +
           d.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"});
  }

  function slice() {
    var n = D.t.length, from = 0;
    if (rangeSec > 0) {
      var cut = D.t[n - 1] - rangeSec;
      for (var i = 0; i < n; i++) { if (D.t[i] >= cut) { from = i; break; } }
      if (from > 0) from -= 1;  // include one point of context before the window
    }
    return {t: D.t.slice(from), v: D.v.slice(from), f: D.f.slice(from), b: D.b.slice(from)};
  }

  function stats(s) {
    var hi = -1e18, lo = 1e18, peak = -1e18, dd = 0;
    for (var i = 0; i < s.v.length; i++) {
      var v = s.v[i];
      if (v > hi) hi = v; if (v < lo) lo = v;
      if (v > peak) peak = v;
      dd = Math.max(dd, 1 - v / peak);
    }
    document.getElementById("ms-ret").textContent = pct(s.v[s.v.length - 1] / s.v[0] - 1);
    document.getElementById("ms-ret").style.color = s.v[s.v.length - 1] >= s.v[0] ? "#0ca30c" : "#e66767";
    document.getElementById("ms-hi").textContent = usd(hi);
    document.getElementById("ms-lo").textContent = usd(lo);
    document.getElementById("ms-dd").textContent = (dd * 100).toFixed(2) + "%";
    document.getElementById("mcount").textContent = s.t.length + " check-ins";
  }

  function render() {
    var s = slice();
    if (s.t.length < 2) return;
    stats(s);
    var W = wrap.clientWidth, H = wrap.clientHeight;
    var padl = 58, padr = 16, padt = 16, padb = 26;
    var lo = 1e18, hi = -1e18;
    for (var i = 0; i < s.v.length; i++) {
      lo = Math.min(lo, s.v[i], s.b[i] || 1e18);
      hi = Math.max(hi, s.v[i], s.b[i] || -1e18);
    }
    var span = (hi - lo) || 1; lo -= span * 0.12; hi += span * 0.12;
    var t0 = s.t[0], t1 = s.t[s.t.length - 1];
    function X(t) { return padl + (t - t0) / ((t1 - t0) || 1) * (W - padl - padr); }
    function Y(v) { return padt + (1 - (v - lo) / (hi - lo)) * (H - padt - padb); }
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", W); svg.setAttribute("height", H);
    function el(tag, attrs, parent) {
      var e = document.createElementNS(svgNS, tag);
      for (var k in attrs) e.setAttribute(k, attrs[k]);
      (parent || svg).appendChild(e); return e;
    }
    for (var g = 0; g <= 2; g++) {
      var gv = lo + (hi - lo) * g / 2, gy = Y(gv);
      el("line", {x1: padl, y1: gy, x2: W - padr, y2: gy, stroke: "#2c2c2a", "stroke-width": 1});
      var txt = el("text", {x: padl - 6, y: gy + 3.5, "text-anchor": "end", "font-size": 10, fill: "#898781"});
      txt.textContent = usd(gv);
    }
    var d0 = el("text", {x: padl, y: H - 8, "font-size": 10, fill: "#898781"});
    d0.textContent = fdate(t0);
    var d1 = el("text", {x: W - padr, y: H - 8, "text-anchor": "end", "font-size": 10, fill: "#898781"});
    d1.textContent = fdate(t1);
    function poly(vals, color, width, cls) {
      var pts = [];
      for (var i = 0; i < vals.length; i++) if (vals[i] != null) pts.push(X(s.t[i]).toFixed(1) + "," + Y(vals[i]).toFixed(1));
      var p = el("polyline", {points: pts.join(" "), fill: "none", stroke: color,
                              "stroke-width": width, "stroke-linejoin": "round", "stroke-linecap": "round"});
      if (cls && !reduced) { p.setAttribute("pathLength", "1"); p.setAttribute("class", cls); }
      return p;
    }
    poly(s.b, "#6a6c72", 1.5);
    // area wash under account line
    var apts = "M " + X(s.t[0]).toFixed(1) + "," + Y(lo).toFixed(1);
    for (var i = 0; i < s.v.length; i++) apts += " L " + X(s.t[i]).toFixed(1) + "," + Y(s.v[i]).toFixed(1);
    apts += " L " + X(s.t[s.t.length - 1]).toFixed(1) + "," + Y(lo).toFixed(1) + " Z";
    el("path", {d: apts, fill: "#3987e5", opacity: reduced ? .08 : 0, "class": reduced ? "" : "wash"});
    poly(s.v, "#3987e5", 2, "draw");
    // fill markers where trades happened
    for (var i = 0; i < s.f.length; i++) if (s.f[i] > 0)
      el("circle", {cx: X(s.t[i]), cy: Y(s.v[i]), r: 3, fill: "#3987e5", stroke: "#16171c", "stroke-width": 2});
    // crosshair layer
    var ch = el("line", {x1: 0, y1: padt, x2: 0, y2: H - padb, stroke: "#52514e", "stroke-width": 1, opacity: 0});
    var dotA = el("circle", {r: 5, fill: "#3987e5", stroke: "#0f1115", "stroke-width": 2, opacity: 0});
    var dotB = el("circle", {r: 4, fill: "#6a6c72", stroke: "#0f1115", "stroke-width": 2, opacity: 0});
    wrap.querySelectorAll("svg").forEach(function(x) { x.remove(); });
    wrap.appendChild(svg);
    view = {s: s, X: X, Y: Y, ch: ch, dotA: dotA, dotB: dotB, W: W, H: H, padl: padl, padr: padr};
  }

  function showAt(idx) {
    if (!view) return;
    var s = view.s, x = view.X(s.t[idx]);
    view.ch.setAttribute("x1", x); view.ch.setAttribute("x2", x); view.ch.setAttribute("opacity", 1);
    view.dotA.setAttribute("cx", x); view.dotA.setAttribute("cy", view.Y(s.v[idx])); view.dotA.setAttribute("opacity", 1);
    if (s.b[idx] != null) {
      view.dotB.setAttribute("cx", x); view.dotB.setAttribute("cy", view.Y(s.b[idx])); view.dotB.setAttribute("opacity", 1);
    } else view.dotB.setAttribute("opacity", 0);
    while (tip.firstChild) tip.removeChild(tip.firstChild);
    function row(color, name, valTxt) {
      var r = document.createElement("div"); r.className = "row";
      var k = document.createElement("span"); k.className = "key"; k.style.background = color;
      var v = document.createElement("span"); v.className = "val"; v.textContent = valTxt;
      var n = document.createElement("span"); n.className = "nm"; n.textContent = name;
      r.appendChild(k); r.appendChild(v); r.appendChild(n); tip.appendChild(r);
    }
    var tt = document.createElement("div"); tt.className = "tt"; tt.textContent = fdate(s.t[idx]); tip.appendChild(tt);
    row("#3987e5", "account · " + pct(s.v[idx] / D.start - 1), usd(s.v[idx]));
    if (s.b[idx] != null) row("#6a6c72", "buy & hold", usd(s.b[idx]));
    if (idx > 0) {
      var chg = document.createElement("div"); chg.className = "tt";
      var dv = s.v[idx] - s.v[idx - 1];
      chg.textContent = (dv >= 0 ? "+" : "−") + "$" + Math.abs(dv).toFixed(0) + " since prior check-in" +
                        (s.f[idx] ? " · " + s.f[idx] + " fills" : " · no trades");
      tip.appendChild(chg);
    }
    tip.style.display = "block";
    var tw = tip.offsetWidth;
    var left = x + 12; if (left + tw > view.W - 8) left = x - tw - 12;
    tip.style.left = Math.max(4, left) + "px";
    tip.style.top = "14px";
  }

  function nearest(clientX) {
    if (!view) return 0;
    var rect = wrap.getBoundingClientRect(), px = clientX - rect.left;
    var s = view.s, best = 0, bd = 1e18;
    for (var i = 0; i < s.t.length; i++) {
      var d = Math.abs(view.X(s.t[i]) - px);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  }
  var curIdx = -1;
  wrap.addEventListener("pointermove", function(e) { curIdx = nearest(e.clientX); showAt(curIdx); });
  wrap.addEventListener("pointerdown", function(e) { curIdx = nearest(e.clientX); showAt(curIdx); });
  wrap.addEventListener("pointerleave", function() {
    tip.style.display = "none";
    if (view) { view.ch.setAttribute("opacity", 0); view.dotA.setAttribute("opacity", 0); view.dotB.setAttribute("opacity", 0); }
  });
  modal.addEventListener("keydown", function(e) {
    if (e.key === "Escape") close();
    if (!view) return;
    if (e.key === "ArrowRight") { curIdx = Math.min(curIdx + 1, view.s.t.length - 1); showAt(curIdx); }
    if (e.key === "ArrowLeft") { curIdx = Math.max(curIdx - 1, 0); showAt(curIdx); }
  });

  document.getElementById("mranges").addEventListener("click", function(e) {
    var b = e.target.closest("button"); if (!b) return;
    this.querySelectorAll("button").forEach(function(x) { x.classList.remove("sel"); });
    b.classList.add("sel");
    rangeSec = parseInt(b.dataset.r, 10);
    render();
  });

  function open() {
    modal.classList.add("open");
    document.body.style.overflow = "hidden";
    modal.setAttribute("tabindex", "-1"); modal.focus();
    requestAnimationFrame(render);
  }
  function close() {
    modal.classList.remove("open");
    document.body.style.overflow = "";
  }
  var panel = document.getElementById("eqpanel");
  if (panel) {
    panel.addEventListener("click", open);
    panel.addEventListener("keydown", function(e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  }
  document.getElementById("mclose").addEventListener("click", close);
  window.addEventListener("resize", function() { if (modal.classList.contains("open")) render(); });
})();
</script>
"""


# ---------------- SVG builders ----------------

def spark(vals, w=110, h=30):
    if len(vals) < 2:
        return f'<svg width="{w}" height="{h}"><line x1="4" y1="{h/2}" x2="{w-8}" y2="{h/2}" stroke="#383835" stroke-width="2" stroke-linecap="round"/></svg>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pad = 5
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * (w - 2 * pad - 6) / (len(vals) - 1)
        y = pad + (1 - (v - lo) / rng) * (h - 2 * pad)
        pts.append((x, y))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg width="{w}" height="{h}" aria-hidden="true">'
            f'<polyline class="spark-draw" pathLength="1" points="{path}" fill="none" stroke="#898781" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle class="enddot" style="animation-delay:.6s" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#3987e5" stroke="{SURFACE}" stroke-width="2"/></svg>')


def equity_chart(points, w=720, h=220):
    """points: [(datetime, equity)] account curve. Single series: no legend."""
    if len(points) < 2:
        return '<div class="sub" style="padding:12px 0">Equity curve appears after a few more check-ins.</div>'
    xs = [p[0].timestamp() for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    lo -= span * 0.15
    hi += span * 0.15
    padl, padr, padt, padb = 62, 14, 12, 26
    tick = (lambda v: f"${v:,.0f}") if (hi - lo) < 3000 else (lambda v: f"${v/1000:,.1f}k")
    iw, ih = w - padl - padr, h - padt - padb

    def X(t):
        return padl + (t - x0) / ((x1 - x0) or 1) * iw

    def Y(v):
        return padt + (1 - (v - lo) / (hi - lo)) * ih

    pts = [(X(t), Y(v)) for t, v in zip(xs, ys)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M {pts[0][0]:.1f},{Y(lo):.1f} L " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L {pts[-1][0]:.1f},{Y(lo):.1f} Z"
    # 3 clean horizontal gridlines
    grid, ticks = [], []
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        y = Y(v)
        grid.append(f'<line x1="{padl}" y1="{y:.1f}" x2="{w-padr}" y2="{y:.1f}" stroke="#2c2c2a" stroke-width="1"/>')
        ticks.append(f'<text x="{padl-6}" y="{y+3.5:.1f}" text-anchor="end" font-size="10" fill="#898781" font-variant-numeric="tabular-nums">{tick(v)}</text>')
    # x labels: first + last date
    d0 = dt.datetime.fromtimestamp(x0).strftime("%d %b")
    d1 = dt.datetime.fromtimestamp(x1).strftime("%d %b %H:%M")
    ex, ey = pts[-1]
    last_lbl = f"${ys[-1]:,.0f}"
    hover_dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="transparent">'
        f'<title>{dt.datetime.fromtimestamp(t).strftime("%d %b %H:%M")} — ${v:,.2f}</title></circle>'
        for (x, y), t, v in zip(pts, xs, ys))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto" role="img" aria-label="Account equity over time">'
            + "".join(grid) + "".join(ticks)
            + f'<path class="wash" d="{area}" fill="#3987e5" opacity="0"/>'
            + f'<polyline class="draw" pathLength="1" points="{line}" fill="none" stroke="#3987e5" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            + f'<circle class="pulsering" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="none" stroke="#3987e5" stroke-width="1.5"/>'
            + f'<circle class="enddot" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#3987e5" stroke="{SURFACE}" stroke-width="2"/>'
            + f'<text class="enddot" x="{min(ex, w-padr-4):.1f}" y="{max(ey-10, 12):.1f}" text-anchor="end" font-size="11" fill="#e8eaed" font-weight="600">{last_lbl}</text>'
            + f'<text x="{padl}" y="{h-8}" font-size="10" fill="#898781">{d0}</text>'
            + f'<text x="{w-padr}" y="{h-8}" text-anchor="end" font-size="10" fill="#898781">{d1}</text>'
            + hover_dots + '</svg>')


def exposure_bars(exposure, total):
    """Horizontal diverging bars: net $ exposure per symbol (blue long / red short)."""
    if not exposure:
        return '<div class="sub">No open positions.</div>'
    mx = max(abs(v) for v in exposure.values()) or 1.0
    rows = []
    for sym, v in sorted(exposure.items(), key=lambda kv: -abs(kv[1])):
        wpct = abs(v) / mx * 100
        color = "#3987e5" if v >= 0 else "#e66767"
        pct = v / total * 100
        rows.append(
            f'<div class="exprow stag" style="--i:{len(rows)}"><div class="explbl">{esc(sym.replace("/USD",""))}</div>'
            f'<div class="exptrack"><div class="expbar" style="--tw:{wpct:.1f}%;background:{color}">'
            f'</div></div><div class="expval">{money(v)} <span class="sub">{pct:+.1f}%</span></div></div>')
    return "".join(rows)


# ---------------- report assembly ----------------

def reconstruct_positions(events, prices):
    """Replay journal fills into average-cost position episodes.
    Returns (open_positions, closed_episodes)."""
    book = {}   # (sleeve, sym) -> {qty, avg, fees, opened, realized}
    closed = []
    for j in events:
        if j.get("type") != "run" or j.get("dry"):
            continue
        ts = j.get("ts", "")[:10]
        for d in j.get("decisions", []):
            key = (d["sleeve"], d["symbol"])
            delta = d["delta_qty"]
            if not delta:
                continue
            px = abs(d["notional"] / delta)
            fee = d.get("fee", 0.0)
            b = book.get(key)
            if b is None or abs(b["qty"]) < 1e-9:
                book[key] = {"qty": delta, "avg": px, "fees": fee, "opened": ts, "realized": 0.0}
                continue
            b["fees"] += fee
            same_dir = (b["qty"] > 0) == (delta > 0)
            if same_dir:  # scale in: weighted average cost
                b["avg"] = (b["avg"] * abs(b["qty"]) + px * abs(delta)) / (abs(b["qty"]) + abs(delta))
                b["qty"] += delta
            else:
                close_qty = min(abs(delta), abs(b["qty"]))
                b["realized"] += (px - b["avg"]) * close_qty * (1 if b["qty"] > 0 else -1)
                remainder = delta + (close_qty if b["qty"] > 0 else -close_qty)
                b["qty"] += delta
                if abs(b["qty"]) * px < 1.0:  # episode fully closed
                    cost = b["avg"] * close_qty
                    pnl = b["realized"] - b["fees"]
                    closed.append({"sleeve": key[0], "symbol": key[1], "opened": b["opened"],
                                   "closed": ts, "pnl": pnl, "fees": b["fees"],
                                   "pct": pnl / cost if cost else 0.0,
                                   "side": "LONG" if delta < 0 else "SHORT"})
                    del book[key]
                elif (b["qty"] > 0) != (delta < 0) and abs(remainder) > 1e-9 and (b["qty"] > 0) != (b["qty"] - delta > 0):
                    # crossed through zero: restart episode on the far side
                    b["avg"], b["opened"], b["fees"], b["realized"] = px, ts, 0.0, 0.0
    opens = []
    for (sleeve, sym), b in book.items():
        px = prices.get(sym, b["avg"])
        upnl = (px - b["avg"]) * b["qty"] - b["fees"] + b["realized"]
        cost = abs(b["qty"]) * b["avg"]
        opens.append({"sleeve": sleeve, "symbol": sym, "qty": b["qty"], "avg": b["avg"],
                      "px": px, "pnl": upnl, "pct": upnl / cost if cost else 0.0,
                      "opened": b["opened"], "side": "LONG" if b["qty"] > 0 else "SHORT"})
    opens.sort(key=lambda x: -abs(x["qty"] * x["px"]))
    closed.sort(key=lambda x: x["closed"], reverse=True)
    return opens, closed


def build(state, prices, flags):
    cap = CFG["sleeve_capital"]
    n = len(CFG["sleeves"])
    now = dt.datetime.now(dt.timezone.utc)

    # journal: account curve + full event history
    curve, events, curve_fills = [], [], []
    jp = os.path.join(HERE, "state", "journal.jsonl")
    if os.path.exists(jp):
        for ln in open(jp):
            try:
                j = json.loads(ln)
            except ValueError:
                continue
            events.append(j)
            if j.get("type") == "run" and not j.get("dry"):
                curve.append((dt.datetime.fromisoformat(j["ts"]).replace(tzinfo=None), j["total_equity"]))
                curve_fills.append(len(j.get("decisions", [])))
    runs = [j for j in events if j.get("type") == "run" and not j.get("dry")]

    # sleeve stats
    stats = {}
    total, total_cash = 0.0, 0.0
    exposure = {}
    for sid in CFG["sleeves"]:
        sv = state["sleeves"][sid]
        eq = sleeve_equity(sv, prices)
        total += eq
        total_cash += sv["cash"]
        for s, q in sv["positions"].items():
            exposure[s] = exposure.get(s, 0.0) + q * prices.get(s, 0.0)
        stats[sid] = {"eq": eq, "ret": eq / cap - 1, "dd": 1 - eq / max(sv["peak"], 1e-9),
                      "hist": [pt[1] for pt in sv["history"]][-40:], "sv": sv}
    tret = total / (cap * n) - 1
    curve.append((now.replace(tzinfo=None), round(total, 2)))
    curve_fills.append(0)

    # interactive-chart payload: account curve + S10 buy&hold rebased to 100k
    s10_hist = [(dt.datetime.fromisoformat(a).replace(tzinfo=None).timestamp(), b)
                for a, b in state["sleeves"]["S10"]["history"]]
    def s10_at(ts):
        best = None
        for t_, v_ in s10_hist:
            if best is None or abs(t_ - ts) < abs(best[0] - ts):
                best = (t_, v_)
        return round(best[1] / cap * cap * n, 2) if best and abs(best[0] - ts) < 43200 else None
    chart_data = {
        "t": [int(p[0].timestamp()) for p in curve],
        "v": [p[1] for p in curve],
        "f": curve_fills,
        "b": [s10_at(p[0].timestamp()) for p in curve],
        "start": cap * n,
    }
    gross = sum(abs(v) for v in exposure.values())
    best = max(stats, key=lambda k: stats[k]["ret"])
    worst = min(stats, key=lambda k: stats[k]["ret"])
    fees = state.get("fees_paid", 0.0)
    acct_dd = 1 - total / max(state.get("account_peak", total), 1e-9)

    up = "#0ca30c" if tret >= 0 else "#d03b3b"

    # flags / status banner
    if state.get("killed"):
        banner = '<div class="flag"><b>ACCOUNT KILL SWITCH ACTIVE</b> — everything flat, awaiting review.</div>'
    elif flags:
        banner = "".join(f'<div class="flag">{esc(f)}</div>' for f in flags)
    else:
        banner = '<div class="ok">All sleeves within risk limits. No flags.</div>'

    # KPI row
    kpis = "".join(f'<div class="kpi"><div class="klabel">{lbl}</div><div class="kval" style="{style}">{val}</div><div class="sub">{sub}</div></div>' for lbl, val, sub, style in [
        ("Best sleeve", f"{best} {stats[best]['ret']:+.2%}", META[best][0], "color:#0ca30c"),
        ("Worst sleeve", f"{worst} {stats[worst]['ret']:+.2%}", META[worst][0], "color:#d03b3b" if stats[worst]['ret'] < 0 else ""),
        ("Gross exposure", f'<span class="anim-num" data-val="{gross/total*100}" data-fmt="pct0" data-final="{gross/total*100:.0f}%">{gross/total*100:.0f}%</span>', f"{money(gross)} deployed", ""),
        ("Cash", f'<span class="anim-num" data-val="{total_cash/total*100}" data-fmt="pct0" data-final="{total_cash/total*100:.0f}%">{total_cash/total*100:.0f}%</span>', f"{money(total_cash)} idle", ""),
        ("Fees paid", f'<span class="anim-num" data-val="{fees}" data-fmt="usd0" data-final="{money(fees)}">{money(fees)}</span>', "5bps stocks / 25bps crypto", ""),
        ("Account drawdown", f'<span class="anim-num" data-val="{acct_dd*100}" data-fmt="pct1" data-final="{acct_dd:.1%}">{acct_dd:.1%}</span>', "kill switch at 20%", ""),
    ])

    # positions ledger
    opens, closed_eps = reconstruct_positions(events, prices)
    tot_upnl = sum(p["pnl"] for p in opens)
    tot_rpnl = sum(c["pnl"] for c in closed_eps)

    def px_fmt(v):
        return f"${v:,.2f}" if v < 1000 else f"${v:,.0f}"

    def prow(p, is_open):
        cls = "pos" if p["pnl"] >= 0 else "neg"
        side_style = "background:#1d2a45;color:#6da7ec" if p["side"] == "LONG" else ""
        side = f'<span class="short" style="{side_style}">{p["side"]}</span>'
        name = META[p["sleeve"]][0]
        if is_open:
            mid = f'{abs(p["qty"]):,.4g} @ {px_fmt(p["avg"])} → now {px_fmt(p["px"])}'
            when = f'opened {p["opened"]}'
        else:
            mid = f'fees ${p["fees"]:.2f}'
            when = f'{p["opened"]} → {p["closed"]}'
        sign = "+" if p["pnl"] >= 0 else "−"
        return (f'<div class="posrow stag" style="--i:{min(p.get("_i",0),14)}" data-sym="{esc(p["symbol"].replace("/USD",""))}" '
                f'data-pnl="{p["pnl"]:.2f}" data-pct="{p["pct"]:.4f}" data-val="{abs(p.get("qty",0)*p.get("px",0)):.2f}"><div><b>{esc(p["symbol"].replace("/USD",""))}</b> {side}'
                f'<div class="sub">{p["sleeve"]} · {esc(name)} · {when}</div>'
                f'<div class="sub">{mid}</div></div>'
                f'<div class="posval {cls}">{sign}${abs(p["pnl"]):,.2f}'
                f'<div class="sub" style="text-align:right">{p["pct"]:+.2%}</div></div></div>')

    for _i, _p in enumerate(opens): _p["_i"] = min(_i, 10)
    for _i, _p in enumerate(closed_eps): _p["_i"] = min(_i, 10)

    def pgroup_html(items, is_open):
        by_sleeve = {}
        for p in items:
            by_sleeve.setdefault(p["sleeve"], []).append(p)
        groups = []
        order = [s for s in CFG["sleeves"] if s in by_sleeve]
        for sid in order:
            rows_ = by_sleeve[sid]
            sub = sum(p["pnl"] for p in rows_)
            scls = "pos" if sub >= 0 else "neg"
            sign = "+" if sub >= 0 else "−"
            body = "".join(prow(p, is_open) for p in rows_)
            groups.append(
                f'<details class="pgroup" data-sleeve="{sid}">'
                f'<summary><span><b>{sid}</b> <span class="cname">{esc(META[sid][0])}</span> '
                f'<span class="sub gcount">{len(rows_)}</span></span>'
                f'<span class="{scls} gsub" style="font-family:var(--disp)">{sign}${abs(sub):,.2f}</span></summary>'
                f'<div class="grows">{body}</div></details>')
        return "".join(groups)

    symchips = "".join(f'<button class="fchip" data-sym="{s.replace("/USD","")}">{s.replace("/USD","")}</button>'
                       for s in CFG["stock_symbols"] + CFG["crypto_symbols"])
    open_html = pgroup_html(opens, True) or '<div class="sub">No open positions.</div>'
    closed_html = pgroup_html(closed_eps, False) or \
                  '<div class="sub">No closed positions yet — every position opened so far is still running.</div>'
    pos_kpis = "".join(f'<div class="kpi"><div class="klabel">{l}</div><div class="kval {c}">{v}</div></div>'
                       for l, v, c in [
        ("Open positions", f'<span class="anim-num" data-val="{len(opens)}" data-fmt="int" data-final="{len(opens)}">{len(opens)}</span>', ""),
        ("Unrealised P/L", f'<span class="anim-num" data-val="{tot_upnl}" data-fmt="usd2s" data-final="{"+" if tot_upnl>=0 else "−"}${abs(tot_upnl):,.2f}">{"+" if tot_upnl>=0 else "−"}${abs(tot_upnl):,.2f}</span>', "pos" if tot_upnl >= 0 else "neg"),
        ("Closed positions", f'<span class="anim-num" data-val="{len(closed_eps)}" data-fmt="int" data-final="{len(closed_eps)}">{len(closed_eps)}</span>', ""),
        ("Realised P/L", f'<span class="anim-num" data-val="{tot_rpnl}" data-fmt="usd2s" data-final="{"+" if tot_rpnl>=0 else "−"}${abs(tot_rpnl):,.2f}">{"+" if tot_rpnl>=0 else "−"}${abs(tot_rpnl):,.2f}</span>', "pos" if tot_rpnl >= 0 else "neg"),
    ])

    # sleeve cards
    cards = []
    for sid in CFG["sleeves"]:
        st = stats[sid]
        sv = st["sv"]
        name, what, weak = META[sid]
        rc = "pos" if st["ret"] >= 0 else "neg"
        posrows = ""
        for s, q in sorted(sv["positions"].items(), key=lambda kv: -abs(kv[1] * prices.get(kv[0], 0))):
            val = q * prices.get(s, 0.0)
            posrows += (f'<tr><td>{esc(s.replace("/USD",""))}{" <span class=short>SHORT</span>" if q<0 else ""}</td>'
                        f'<td class="num">{abs(q):,.4g}</td><td class="num">{money(val)}</td>'
                        f'<td class="num">{val/st["eq"]*100:.0f}%</td></tr>')
        pos_html = (f'<table class="postable"><tr class="sub"><td>Position</td><td class="num">Qty</td><td class="num">Value</td><td class="num">of sleeve</td></tr>{posrows}</table>'
                    if posrows else '<div class="sub" style="margin-top:6px">No open positions — the signal is flat, which is a decision too.</div>')
        flat = ' <span class="short" style="background:#452020">FROZEN 15% DD</span>' if sv["flattened"] else ""
        cards.append(f'''<details class="card stag" style="--i:{min(len(cards),14)}">
<summary><div class="cardhead"><div><b>{sid}</b> <span class="cname">{esc(name)}</span>{flat}</div>
<div class="cardright"><span class="{rc}">{st["ret"]:+.2%}</span>{spark(st["hist"])}</div></div></summary>
<div class="dwrap"><div class="cardbody">
<p class="what">{esc(what)}</p>
<p class="weak"><b>Known weakness:</b> {esc(weak)}</p>
<div class="statline"><span>Equity <b>{money(st["eq"])}</b></span><span>Drawdown <b>{st["dd"]:.1%}</b></span><span>Cash <b>{money(sv["cash"])}</b></span></div>
{pos_html}
</div></div></details>''')

    # full check-in history: every journaled event, newest first.
    # Last 60 runs are expandable with full decisions; older runs get one summary line.
    feed, run_count = [], 0
    for j in reversed(events):
        ts = j.get("ts", "")[:16].replace("T", " ") + "Z"
        typ = j.get("type")
        if typ == "note":
            kind = j.get("kind", "note")
            chip = ('<span class="chip rev">REVIEW</span>' if kind == "review"
                    else '<span class="chip dec">DECISION</span>')
            feed.append(f'<div class="note"><div class="sub" style="margin-bottom:3px">{ts}</div>{chip}{esc(j.get("text",""))}</div>')
        elif typ == "error":
            feed.append(f'<div class="flag">{ts} · {esc(j.get("msg",""))}</div>')
        elif typ == "run":
            run_count += 1
            dry = " · DRY" if j.get("dry") else ""
            nd = len(j.get("decisions", []))
            head = (f'{ts}{dry} · equity <b>{money(j.get("total_equity",0))}</b> · '
                    f'{nd} fill{"s" if nd != 1 else ""} · dd {j.get("account_dd",0)*100:.1f}%')
            fl = "".join(f'<div class="flag">{esc(f)}</div>' for f in j.get("flags", []))
            if run_count > 60:
                feed.append(f'<div class="act sub">{head}</div>{fl}')
                continue
            items = []
            for d in j.get("decisions", []):
                verb = "bought" if d["notional"] > 0 else "sold"
                items.append(f'<div class="act"><b>{d["sleeve"]}</b> {verb} {esc(d["symbol"].replace("/USD",""))} {money(abs(d["notional"]))} <span class="sub">→ target {d["target_w"]*100:.0f}% · fee ${d["fee"]:.2f}</span></div>')
            body = "".join(items) or '<div class="act sub">No trades — every sleeve already at target (holding is a decision too).</div>'
            feed.append(f'<details class="runcard"><summary class="act" style="cursor:pointer">{head}</summary><div class="dwrap">{fl}<div style="padding-left:8px">{body}</div></div></details>')

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="{PAGE}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>if('serviceWorker' in navigator){{navigator.serviceWorker.register('sw.js');}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<title>Strategy Test — Full Report</title><style>
:root{{color-scheme:dark;--disp:'Space Grotesk',system-ui,sans-serif;--body:'Inter',system-ui,-apple-system,sans-serif}}
body{{font-family:var(--body);margin:0;background:{PAGE};color:#e8eaed;padding:14px;max-width:760px;margin:0 auto}}
h1{{font-family:var(--disp);font-size:1.05rem;margin:18px 0 6px;color:#c3c2b7;font-weight:600;letter-spacing:.06em;text-transform:uppercase;font-size:.78rem}}
.hero{{font-family:var(--disp);font-size:3.1rem;font-weight:700;line-height:1.05;margin:2px 0;letter-spacing:-.01em}}
.sub{{color:#898781;font-size:.78rem}} .pos{{color:#0ca30c;font-weight:600}} .neg{{color:#e66767;font-weight:600}}
.panel{{background:{SURFACE};border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:14px;margin:10px 0}}
.flag{{background:#452020;border-left:3px solid #d03b3b;padding:9px 10px;margin:8px 0;border-radius:6px;font-size:.85rem}}
.ok{{background:#15251a;border-left:3px solid #0ca30c;padding:9px 10px;margin:8px 0;border-radius:6px;font-size:.85rem}}
.kpis{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.kpi{{background:{SURFACE};border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:10px}}
.klabel{{color:#898781;font-size:.72rem;margin-bottom:2px}} .kval{{font-family:var(--disp);font-size:1.08rem;font-weight:600}}
.exprow{{display:flex;align-items:center;gap:8px;margin:7px 0}}
.explbl{{width:44px;font-size:.8rem;font-weight:600}}
.exptrack{{flex:1;height:14px;position:relative}}
.expbar{{height:14px;border-radius:0 4px 4px 0;min-width:2px;width:0;transition:width .9s cubic-bezier(.2,.7,.25,1)}}
.go .expbar{{width:var(--tw)}}
.expval{{width:120px;text-align:right;font-size:.78rem;font-variant-numeric:tabular-nums}}
.card{{background:{SURFACE};border:1px solid rgba(255,255,255,.07);border-radius:12px;margin:8px 0;overflow:hidden}}
.card summary{{list-style:none;cursor:pointer;padding:11px 12px}}
.card summary::-webkit-details-marker{{display:none}}
.cardhead{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
.cname{{color:#c3c2b7;font-size:.85rem}} .cardright{{display:flex;align-items:center;gap:10px}}
.cardbody{{padding:0 12px 12px;border-top:1px solid rgba(255,255,255,.06)}}
.what{{font-size:.85rem;color:#e8eaed;margin:10px 0 4px}}
.weak{{font-size:.78rem;color:#898781;margin:4px 0 8px}}
.statline{{display:flex;gap:16px;font-size:.78rem;color:#898781;margin:8px 0}}
.statline b{{color:#e8eaed;font-weight:600}}
.postable{{width:100%;border-collapse:collapse;margin-top:4px}}
.postable td{{padding:5px 4px;border-bottom:1px solid rgba(255,255,255,.06);font-size:.82rem}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.short{{background:#3a2530;color:#e66767;font-size:.65rem;padding:1px 5px;border-radius:4px;font-weight:700}}
.act{{font-size:.82rem;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05)}}
.runcard summary{{list-style:none}} .runcard summary::-webkit-details-marker{{display:none}}
.runcard summary::before{{content:"▸ ";color:#898781}} .runcard[open] summary::before{{content:"▾ "}}
.note{{background:#1d2333;border-left:3px solid #3987e5;padding:9px 10px;margin:8px 0;border-radius:6px;font-size:.85rem}}
.posrow{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06)}}
.posrow:last-child{{border-bottom:none}}
.posval{{font-family:var(--disp);font-weight:600;font-size:.95rem;white-space:nowrap;font-variant-numeric:tabular-nums}}
.fbar{{position:sticky;top:46px;z-index:8;background:rgba(15,17,21,.94);backdrop-filter:blur(10px);margin:6px -14px 0;padding:8px 14px;border-bottom:1px solid rgba(255,255,255,.05)}}
.fchips{{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding-bottom:6px}}
.fchips::-webkit-scrollbar{{display:none}}
.fchip{{background:#16171c;border:1px solid rgba(255,255,255,.08);border-radius:999px;color:#898781;padding:5px 13px;font-size:.75rem;font-family:var(--disp);font-weight:600;cursor:pointer;white-space:nowrap}}
.fchip.sel{{background:#1d2a45;border-color:#3987e5;color:#6da7ec}}
.frow2{{display:flex;gap:8px;justify-content:space-between}}
.fseg{{display:flex;background:#16171c;border:1px solid rgba(255,255,255,.08);border-radius:8px;overflow:hidden}}
.fseg button{{background:none;border:none;color:#898781;padding:5px 11px;font-size:.72rem;font-family:var(--disp);font-weight:600;cursor:pointer}}
.fseg button.sel{{background:#1d2a45;color:#6da7ec}}
.pgroup{{border-bottom:1px solid rgba(255,255,255,.06)}}
.pgroup:last-child{{border-bottom:none}}
.pgroup summary{{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:10px 0}}
.pgroup summary::-webkit-details-marker{{display:none}}
.pgroup summary > span:first-child::before{{content:"▸";color:#898781;margin-right:8px}}
.pgroup[open] summary > span:first-child::before{{content:"▾"}}
.gcount{{background:#22242b;border-radius:999px;padding:1px 8px;margin-left:6px;font-size:.68rem}}
.grows{{padding-left:6px}}
.posarea.flat .pgroup summary{{display:none}}
.posarea.flat .pgroup{{border:none}}
.posarea.flat .grows{{padding-left:0}}
section.tab{{display:none}} section.tab.active{{display:block;animation:tabin .32s cubic-bezier(.2,.7,.3,1)}}
@keyframes tabin{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
@keyframes fadein{{to{{opacity:1}}}}
@keyframes areain{{to{{opacity:.10}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
@keyframes pulse{{0%{{transform:scale(1);opacity:.55}}70%{{transform:scale(2.6);opacity:0}}100%{{transform:scale(2.6);opacity:0}}}}
.draw{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.2s .1s cubic-bezier(.4,0,.2,1) forwards}}
.spark-draw{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw .7s .15s ease-out forwards}}
.wash{{opacity:0;animation:areain .6s .9s ease forwards}}
.enddot{{opacity:0;animation:fadein .4s 1.15s ease forwards}}
.pulsering{{opacity:0;animation:fadein .1s 1.3s forwards, pulse 2.2s 1.4s ease-out 3;transform-origin:center;transform-box:fill-box}}
.stag{{animation:rise .38s cubic-bezier(.2,.7,.3,1) both;animation-delay:calc(var(--i,0)*40ms)}}
@media (prefers-reduced-motion: reduce){{
  *,*::before,*::after{{animation-duration:.01ms!important;animation-delay:0ms!important;transition-duration:.01ms!important}}
}}
nav.tabs{{position:fixed;bottom:0;left:0;right:0;display:flex;background:rgba(15,17,21,.92);backdrop-filter:blur(12px);border-top:1px solid rgba(255,255,255,.08);padding-bottom:env(safe-area-inset-bottom);z-index:10}}
nav.tabs a{{flex:1;text-align:center;padding:9px 0 7px;text-decoration:none;color:#898781;font-size:.66rem;line-height:1.3}}
nav.tabs a svg{{display:block;margin:0 auto 2px;width:20px;height:20px}}
nav.tabs a.active{{color:#3987e5;font-weight:600}}
.chip{{display:inline-block;font-size:.62rem;font-weight:700;letter-spacing:.06em;padding:2px 7px;border-radius:4px;vertical-align:1px;margin-right:6px}}
.chip.dec{{background:#1d2a45;color:#6da7ec}} .chip.rev{{background:#2a2438;color:#9085e9}}
.topbar{{position:sticky;top:0;background:rgba(15,17,21,.92);backdrop-filter:blur(12px);z-index:9;padding:10px 0 8px;margin:0 -14px;padding-left:14px;padding-right:14px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;justify-content:space-between;align-items:baseline}}
.doc p{{font-size:.85rem;color:#c3c2b7;line-height:1.5}}
.doc b{{color:#e8eaed}}
footer{{margin:22px 0 10px;color:#898781;font-size:.72rem;line-height:1.5}}
body{{padding-bottom:76px}}
</style></head><body>
<div class="topbar"><span style="font-family:var(--disp);font-weight:700;letter-spacing:.01em">Strategy Test</span>
<span class="{'pos' if tret>=0 else 'neg'}" style="font-family:var(--disp);font-size:.95rem">{tret:+.2%} · {money(total)}</span></div>

<section class="tab" id="overview">
<div class="sub" style="margin-top:10px">SIMULATED $100,000 · 20 SLEEVES · 7 SYMBOLS</div>
<div class="hero" style="color:{up}"><span class="anim-num" data-val="{tret*100}" data-fmt="pct2" data-final="{tret:+.2%}">{tret:+.2%}</span></div>
<div class="sub">{money(total)} total · updated {now.strftime('%a %d %b %Y, %H:%M')} UTC · day {max(1,(now.date()-dt.date(2026,7,13)).days+1)} of ~90</div>
{banner}
<h1>Account equity</h1>
<div class="panel" id="eqpanel" role="button" tabindex="0" aria-label="Open interactive equity chart" style="cursor:pointer">{equity_chart(curve)}
<div class="sub" style="text-align:center;margin-top:4px">Tap for interactive view</div></div>
<h1>Vitals</h1>
<div class="kpis">{kpis}</div>
<h1>Net exposure by symbol</h1>
<div class="panel">{exposure_bars(exposure, total)}
<div class="sub" style="margin-top:8px">Blue = net long, red = net short, summed across all 20 sleeves. % is of total account equity.</div></div>
</section>

<section class="tab" id="positions">
<h1 style="margin-top:14px">Position P/L</h1>
<div class="kpis">{pos_kpis}</div>
<div class="fbar">
<div class="fchips" id="symchips"><button class="fchip sel" data-sym="">All</button>{symchips}</div>
<div class="frow2">
<div class="fseg" id="viewseg"><button class="sel" data-view="group">By strategy</button><button data-view="flat">Flat</button></div>
<div class="fseg" id="sortseg"><button class="sel" data-sort="val">Size</button><button data-sort="pnl">P/L</button><button data-sort="pct">P/L %</button></div>
</div></div>
<div class="sub" style="margin:8px 2px">Net of fees. Each strategy runs its own book, so a symbol can appear once per sleeve. Tap a strategy group to expand; subtotal on the right.</div>
<h1>Open positions <span class="sub" id="opencount"></span></h1>
<div class="panel posarea" id="openarea">{open_html}</div>
<h1>Closed positions <span class="sub" id="closedcount"></span></h1>
<div class="panel posarea" id="closedarea">{closed_html}</div>
</section>

<section class="tab" id="strategies">
<h1 style="margin-top:14px">Strategy sleeves — tap to expand</h1>
{"".join(cards)}
</section>

<section class="tab" id="history">
<h1 style="margin-top:14px">Check-in history — every session, every decision</h1>
<div class="panel">
<div class="sub" style="margin-bottom:6px">{len(runs)} check-ins journaled. Tap a session to see its fills. Blue cards are strategic decisions by the reviewing agent; violet cards are weekly reviews.</div>
{"".join(feed) or '<div class="sub">No runs journaled yet.</div>'}</div>
</section>

<section class="tab" id="about">
<h1 style="margin-top:14px">How this test works</h1>
<div class="panel doc">
<p><b>Setup.</b> $100,000 of simulated money split into twenty $5,000 sleeves. S1–S10 run the same rules independently on each of 7 symbols (SPY, NVDA, AAPL, MSFT, BTC, ETH, SOL); P1–P10 trade the whole universe as a portfolio. Fills happen at live fetched prices <b>minus a fee/slippage haircut</b> (5bps stocks, 25bps crypto) — deliberately harsher than most paper-trading platforms, which fill at perfect prices.</p>
<p><b>Risk rules (enforced in code).</b> A sleeve losing 15% from its peak is frozen and flagged for review. No sleeve may exceed 1.5× its capital. If the whole account draws down 20%, everything goes flat and stays flat until the human says otherwise.</p>
<p><b>Judgment discipline.</b> No strategy is declared good or bad before 60 trading days — earlier kills happen only for broken behavior, never for losing. Strategy rules are frozen for the duration: improvement ideas get logged, not applied, because a test whose rules drift measures nothing. The benchmark is S10 (buy &amp; hold): any sleeve that can't beat it after costs has no reason to exist.</p>
<p><b>What we honestly expect.</b> Over one quarter, most of these 20 will be statistically indistinguishable from noise. The genuinely interesting outputs are the ensemble-vs-members comparison (P7), the regime switcher (P10), and learning which strategy <i>types</i> suit which market regimes.</p>
<p><b>Operations.</b> Checked twice daily (07:00 & 20:15 UTC) by scheduled runs that refresh data, execute signals, apply risk rules, journal every decision with its reason, and republish this page. Crypto data: Kraken. Stocks: Alpha Vantage (daily bars). The full project — code, data, and this journal — is version-controlled on every run.</p>
<p><b>Pre-registered evaluation.</b> The final judgment happens on <b>12 Oct 2026</b> against criteria frozen on 14 Jul 2026, before results existed (EVALUATION.md in the repo). Sleeves can be killed for excessive costs (&gt;3%/yr fee drag), redundancy (&gt;0.90 return correlation with a cheaper twin), or failing to match their own backtest (&lt;0.60 consistency) — but never for simply losing, and no live strategy's parameters are ever edited; a "tweak" becomes a new sleeve with a fresh track record. Every reported Sharpe carries a bootstrap 95% confidence interval, because a quarter of daily data cannot rank strategies honestly without one. A frozen-rules backtest over the prior 9 months (a crypto-bear regime: buy-and-hold −29%) provides each sleeve's baseline expectation.</p>
</div>
<footer>Simulated money only — nothing here is investment advice, and paper results overstate live results even with the fee haircut. Data: Kraken (crypto, 24/7), Alpha Vantage (US equities, daily). Page refreshes at every check-in; installed as an app it shows the last snapshot when offline.</footer>
</section>

<nav class="tabs">
<a href="#overview" data-tab="overview"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-6 4 3 6-8"/><path d="M3 21h18"/></svg>Overview</a>
<a href="#positions" data-tab="positions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16v13H4z"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M4 13h16"/></svg>Positions</a>
<a href="#strategies" data-tab="strategies"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>Strategies</a>
<a href="#history" data-tab="history"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>History</a>
<a href="#about" data-tab="about"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>About</a>
</nav>
<script>
(function() {{
  var tabs = ["overview","positions","strategies","history","about"];
  function show() {{
    var t = location.hash.replace("#","");
    if (tabs.indexOf(t) < 0) t = "overview";
    tabs.forEach(function(id) {{
      document.getElementById(id).classList.toggle("active", id === t);
    }});
    document.querySelectorAll("nav.tabs a").forEach(function(a) {{
      a.classList.toggle("active", a.dataset.tab === t);
    }});
    window.scrollTo(0, 0);
  }}
  window.addEventListener("hashchange", show);
  show();

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function fmtNum(v, f) {{
    if (f === "pct2") return (v >= 0 ? "+" : "\u2212") + Math.abs(v).toFixed(2) + "%";
    if (f === "pct1") return v.toFixed(1) + "%";
    if (f === "pct0") return Math.round(v) + "%";
    if (f === "usd0") return "$" + Math.round(v).toLocaleString();
    if (f === "usd2s") return (v >= 0 ? "+$" : "\u2212$") + Math.abs(v).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
    return Math.round(v).toLocaleString();
  }}
  function runCounter(el) {{
    if (el.dataset.done) return;
    el.dataset.done = "1";
    var v = parseFloat(el.dataset.val), f = el.dataset.fmt, fin = el.dataset.final || el.textContent;
    if (reduced || isNaN(v)) {{ el.textContent = fin; return; }}
    var t0 = null, dur = 950;
    function step(t) {{
      if (!t0) t0 = t;
      var p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmtNum(v * e, f);
      if (p < 1) requestAnimationFrame(step); else el.textContent = fin;
    }}
    requestAnimationFrame(step);
  }}
  var io = new IntersectionObserver(function(es) {{
    es.forEach(function(en) {{ if (en.isIntersecting) {{ runCounter(en.target); io.unobserve(en.target); }} }});
  }}, {{threshold: 0.4}});
  document.querySelectorAll(".anim-num").forEach(function(el) {{ io.observe(el); }});

  // sliding exposure bars: re-run whenever their tab is shown
  function armBars() {{
    var sec = document.querySelector("section.tab.active");
    if (!sec) return;
    sec.querySelectorAll(".panel").forEach(function(p) {{ p.classList.remove("go"); }});
    requestAnimationFrame(function() {{ requestAnimationFrame(function() {{
      sec.querySelectorAll(".panel").forEach(function(p) {{ p.classList.add("go"); }});
    }}); }});
  }}
  window.addEventListener("hashchange", armBars);
  armBars();

  // measured-height slide for every expandable card

  // ---- positions tab: filter / view / sort
  (function() {{
    var symSel = "", viewMode = "group", sortKey = "val";
    var areas = [document.getElementById("openarea"), document.getElementById("closedarea")];
    if (!areas[0]) return;

    function apply() {{
      areas.forEach(function(area) {{
        if (!area) return;
        area.classList.toggle("flat", viewMode === "flat");
        var shown = 0;
        area.querySelectorAll(".pgroup").forEach(function(g) {{
          var vis = 0, sub = 0;
          var rows = Array.prototype.slice.call(g.querySelectorAll(".posrow"));
          rows.forEach(function(r) {{
            var ok = !symSel || r.dataset.sym === symSel;
            r.style.display = ok ? "" : "none";
            if (ok) {{ vis++; sub += parseFloat(r.dataset.pnl) || 0; }}
          }});
          rows.sort(function(a, b) {{
            return (parseFloat(b.dataset[sortKey]) || 0) - (parseFloat(a.dataset[sortKey]) || 0);
          }});
          var host = g.querySelector(".grows");
          rows.forEach(function(r) {{ host.appendChild(r); }});
          g.style.display = vis ? "" : "none";
          if (viewMode === "flat") g.open = true;
          var cnt = g.querySelector(".gcount"), subEl = g.querySelector(".gsub");
          if (cnt) cnt.textContent = vis;
          if (subEl) {{
            subEl.textContent = (sub >= 0 ? "+$" : "\u2212$") + Math.abs(sub).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            subEl.className = (sub >= 0 ? "pos" : "neg") + " gsub";
            subEl.style.fontFamily = "var(--disp)";
          }}
          shown += vis;
        }});
        var lbl = document.getElementById(area.id === "openarea" ? "opencount" : "closedcount");
        if (lbl) lbl.textContent = "· " + shown + " shown";
      }});
    }}

    document.getElementById("symchips").addEventListener("click", function(e) {{
      var b = e.target.closest(".fchip"); if (!b) return;
      this.querySelectorAll(".fchip").forEach(function(x) {{ x.classList.remove("sel"); }});
      b.classList.add("sel");
      symSel = b.dataset.sym;
      apply();
    }});
    document.getElementById("viewseg").addEventListener("click", function(e) {{
      var b = e.target.closest("button"); if (!b) return;
      this.querySelectorAll("button").forEach(function(x) {{ x.classList.remove("sel"); }});
      b.classList.add("sel");
      viewMode = b.dataset.view;
      if (viewMode === "group") {{
        areas.forEach(function(a) {{ if (a) a.querySelectorAll(".pgroup").forEach(function(g) {{ g.open = false; }}); }});
      }}
      apply();
    }});
    document.getElementById("sortseg").addEventListener("click", function(e) {{
      var b = e.target.closest("button"); if (!b) return;
      this.querySelectorAll("button").forEach(function(x) {{ x.classList.remove("sel"); }});
      b.classList.add("sel");
      sortKey = b.dataset.sort;
      apply();
    }});
    apply();
  }})();

  document.querySelectorAll("details.card, details.runcard").forEach(function(d) {{
    var s = d.querySelector("summary"), c = d.querySelector(":scope > .dwrap");
    if (!s || !c) return;
    s.addEventListener("click", function(e) {{
      e.preventDefault();
      if (reduced) {{ d.open = !d.open; return; }}
      if (!d.open) {{
        d.open = true;
        var h = c.scrollHeight;
        c.style.height = "0px"; c.style.overflow = "hidden";
        requestAnimationFrame(function() {{
          c.style.transition = "height .34s cubic-bezier(.2,.7,.3,1)";
          c.style.height = h + "px";
          c.addEventListener("transitionend", function() {{ c.style.cssText = ""; }}, {{once: true}});
        }});
      }} else {{
        var h = c.scrollHeight;
        c.style.height = h + "px"; c.style.overflow = "hidden";
        requestAnimationFrame(function() {{
          c.style.transition = "height .26s ease";
          c.style.height = "0px";
          c.addEventListener("transitionend", function() {{ d.open = false; c.style.cssText = ""; }}, {{once: true}});
        }});
      }}
    }});
  }});
}})();
</script>
</body></html>'''
    html = html.replace("</body></html>",
                        MODAL.replace("__DATA__", json.dumps(chart_data)) + "\n</body></html>")
    with open(OUT, "w") as f:
        f.write(html)
    pub = os.path.join(HERE, "docs")
    if os.path.isdir(pub):
        with open(os.path.join(pub, "index.html"), "w") as f:
            f.write(html)
    return OUT
