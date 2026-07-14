"""20 strategy sleeves. Each returns target weights {symbol: fraction_of_sleeve_equity}
or None meaning "no rebalance today, keep current holdings".

Stateful entries/exits use sleeve["memo"] (a dict persisted in state.json).
Negative weights = short (equities only; crypto sleeves are long-only by construction).
"""
import json
import os

import numpy as np
import pandas as pd

import indicators as ind

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
ALL = CFG["stock_symbols"] + CFG["crypto_symbols"]
N = len(ALL)
EW = 1.0 / N  # equal weight per symbol inside a per-symbol sleeve


def _holding(sleeve, sym):
    return sleeve["positions"].get(sym, 0.0) > 0


# ---------- stateless vote signals (used by S-sleeves, P7 ensemble, P10 regime) ----------

def votes(df: pd.DataFrame) -> dict:
    c = df["close"]
    if len(c) < 210:
        return {f"v{i}": False for i in range(1, 10)}
    sma20, sma50, sma200 = ind.sma(c, 20), ind.sma(c, 50), ind.sma(c, 200)
    rsi2 = ind.rsi(c, 2)
    lob, midb, upb = ind.bollinger(c)
    lok, midk, upk = ind.keltner(df)
    line, sig, hist = ind.macd(c)
    v = {}
    v["v1"] = sma20.iloc[-1] > sma50.iloc[-1]
    v["v2"] = c.iloc[-1] > sma200.iloc[-1] and rsi2.iloc[-1] < 10
    v["v3"] = c.iloc[-1] < lob.iloc[-1]
    v["v4"] = c.iloc[-1] > c.rolling(20).max().shift(1).iloc[-1]
    v["v5"] = line.iloc[-1] > sig.iloc[-1] and hist.iloc[-1] > hist.iloc[-2]
    v["v6"] = ind.roc(c, 90).iloc[-1] > 0
    vol = ind.realized_vol(c, 20)
    v["v7"] = v["v6"] and vol.iloc[-1] < vol.rolling(252, min_periods=60).median().iloc[-1]
    squeeze_prev = lob.iloc[-2] > lok.iloc[-2] and upb.iloc[-2] < upk.iloc[-2]
    v["v8"] = squeeze_prev and c.iloc[-1] > upk.iloc[-1]
    v["v9"] = (c.iloc[-1] > sma200.iloc[-1]
               and c.iloc[-1] < c.iloc[-2] < c.iloc[-3] < c.iloc[-4])
    return {k: bool(x) for k, x in v.items()}


# ---------- Part A: per-symbol sleeves ----------

def s1(bars, sleeve, now):
    return {s: (EW if votes(bars[s])["v1"] else 0.0) for s in ALL}


def s2(bars, sleeve, now):
    t, memo = {}, sleeve["memo"]
    for s in ALL:
        c = bars[s]["close"]
        rsi2 = ind.rsi(c, 2).iloc[-1]
        held = memo.get(f"s2_{s}")
        if _holding(sleeve, s) and held is not None:
            days = (pd.Timestamp(now.date()) - pd.Timestamp(held)).days
            if rsi2 > 70 or days >= 5:
                t[s] = 0.0
                memo.pop(f"s2_{s}", None)
            else:
                t[s] = EW
        elif votes(bars[s])["v2"]:
            t[s] = EW
            memo[f"s2_{s}"] = str(now.date())
        else:
            t[s] = 0.0
    return t


def s3(bars, sleeve, now):
    t, memo = {}, sleeve["memo"]
    for s in ALL:
        df = bars[s]
        c = df["close"].iloc[-1]
        lob, midb, _ = ind.bollinger(df["close"])
        a = ind.atr(df).iloc[-1]
        entry = memo.get(f"s3_{s}")
        if _holding(sleeve, s) and entry is not None:
            if c >= midb.iloc[-1] or c < entry - 2 * a:
                t[s] = 0.0
                memo.pop(f"s3_{s}", None)
            else:
                t[s] = EW
        elif c < lob.iloc[-1]:
            t[s] = EW
            memo[f"s3_{s}"] = float(c)
        else:
            t[s] = 0.0
    return t


def s4(bars, sleeve, now):
    t = {}
    for s in ALL:
        c = bars[s]["close"]
        hi20 = c.rolling(20).max().shift(1).iloc[-1]
        lo10 = c.rolling(10).min().shift(1).iloc[-1]
        if _holding(sleeve, s):
            t[s] = 0.0 if c.iloc[-1] <= lo10 else EW
        else:
            t[s] = EW if c.iloc[-1] > hi20 else 0.0
    return t


def s5(bars, sleeve, now):
    t = {}
    for s in ALL:
        line, sig, _ = ind.macd(bars[s]["close"])
        if _holding(sleeve, s):
            t[s] = EW if line.iloc[-1] > sig.iloc[-1] else 0.0
        else:
            t[s] = EW if votes(bars[s])["v5"] else 0.0
    return t


def s6(bars, sleeve, now):
    return {s: (EW if votes(bars[s])["v6"] else 0.0) for s in ALL}


def s7(bars, sleeve, now):
    t = {}
    for s in ALL:
        c = bars[s]["close"]
        if ind.roc(c, 90).iloc[-1] > 0:
            vol = ind.realized_vol(c, 20).iloc[-1]
            t[s] = EW * min(1.0, 0.10 / max(vol, 1e-6)) if np.isfinite(vol) else 0.0
        else:
            t[s] = 0.0
    return t


def s8(bars, sleeve, now):
    t = {}
    for s in ALL:
        df = bars[s]
        if _holding(sleeve, s):
            ema10 = ind.ema(df["close"], 10).iloc[-1]
            t[s] = 0.0 if df["close"].iloc[-1] < ema10 else EW
        else:
            t[s] = EW if votes(df)["v8"] else 0.0
    return t


def s9(bars, sleeve, now):
    t, memo = {}, sleeve["memo"]
    for s in ALL:
        c = bars[s]["close"]
        held = memo.get(f"s9_{s}")
        if _holding(sleeve, s) and held is not None:
            days = (pd.Timestamp(now.date()) - pd.Timestamp(held)).days
            if c.iloc[-1] > c.iloc[-2] or days >= 7:
                t[s] = 0.0
                memo.pop(f"s9_{s}", None)
            else:
                t[s] = EW
        elif votes(bars[s])["v9"]:
            t[s] = EW
            memo[f"s9_{s}"] = str(now.date())
        else:
            t[s] = 0.0
    return t


def s10(bars, sleeve, now):
    return {s: EW for s in ALL}  # engine's min-trade threshold stops daily micro-churn


# ---------- Part B: portfolio sleeves ----------

def _weekly(sleeve, now):
    """True if we should rebalance (Mondays, or never traded yet)."""
    return now.weekday() == 0 or not sleeve.get("ever_traded")


def p1(bars, sleeve, now):
    r30 = {s: ind.roc(bars[s]["close"], 30).iloc[-1] for s in ALL}
    ranked = sorted(ALL, key=lambda s: r30[s], reverse=True)
    current = [s for s, q in sleeve["positions"].items() if q > 0]
    top2 = ranked[:2]
    keep = []
    for c in current:
        if c in top2:
            keep.append(c)
        else:  # hysteresis: only evict if a challenger beats incumbent by >2%
            challenger = next((s for s in top2 if s not in current and s not in keep), None)
            if challenger and r30[challenger] > r30[c] + 0.02:
                keep.append(challenger)
            else:
                keep.append(c)
    new = (keep + [s for s in top2 if s not in keep])[:2] if keep else top2
    return {s: (0.5 if s in new else 0.0) for s in ALL}


def p2(bars, sleeve, now):
    if not _weekly(sleeve, now):
        return None
    iv = {s: 1.0 / max(ind.realized_vol(bars[s]["close"], 20).iloc[-1], 1e-6) for s in ALL}
    tot = sum(iv.values())
    return {s: iv[s] / tot for s in ALL}


def p3(bars, sleeve, now):
    if not _weekly(sleeve, now):
        return None
    r90 = {s: ind.roc(bars[s]["close"], 90).iloc[-1] for s in ALL}
    best = max(ALL, key=lambda s: r90[s])
    if r90[best] <= 0:
        return {s: 0.0 for s in ALL}
    return {s: (1.0 if s == best else 0.0) for s in ALL}


def p4(bars, sleeve, now):
    ratio = (bars["ETH/USD"]["close"] / bars["BTC/USD"]["close"]).dropna()
    z = (ratio.iloc[-1] - ratio.rolling(60).mean().iloc[-1]) / max(ratio.rolling(60).std().iloc[-1], 1e-9)
    memo = sleeve["memo"]
    if z < -1.5:
        memo["p4"] = "eth"
    elif z > 1.5:
        memo["p4"] = "btc"
    elif abs(z) < 0.5:
        memo["p4"] = "neutral"
    tilt = memo.get("p4", "neutral")
    w = {"eth": {"ETH/USD": 0.75, "BTC/USD": 0.25},
         "btc": {"ETH/USD": 0.25, "BTC/USD": 0.75},
         "neutral": {"ETH/USD": 0.5, "BTC/USD": 0.5}}[tilt]
    out = {s: 0.0 for s in ALL}
    out.update(w)
    return out


def p5(bars, sleeve, now):
    a, m = bars["AAPL"]["close"], bars["MSFT"]["close"]
    n = min(len(a), len(m))
    a, m = np.log(a.iloc[-n:].values), np.log(m.iloc[-n:].values)
    if n < 70:
        return {s: 0.0 for s in ALL}
    beta = np.polyfit(m[-60:], a[-60:], 1)[0]
    spread = a[-60:] - beta * m[-60:]
    z = (spread[-1] - spread.mean()) / max(spread.std(), 1e-9)
    memo, pos = sleeve["memo"], sleeve["memo"].get("p5", "flat")
    if pos == "flat":
        if z > 2.0:
            memo["p5"] = "short_spread"   # spread rich: short AAPL, long MSFT
        elif z < -2.0:
            memo["p5"] = "long_spread"    # spread cheap: long AAPL, short MSFT
    else:
        if abs(z) < 0.5 or abs(z) > 3.5:
            memo["p5"] = "flat"
    pos = memo.get("p5", "flat")
    out = {s: 0.0 for s in ALL}
    if pos == "short_spread":
        out.update({"AAPL": -0.5, "MSFT": 0.5})
    elif pos == "long_spread":
        out.update({"AAPL": 0.5, "MSFT": -0.5})
    return out


def p6(bars, sleeve, now):
    if not _weekly(sleeve, now):
        return None
    crypto = ["BTC/USD", "ETH/USD", "SOL/USD"]
    cr = float(np.mean([ind.roc(bars[s]["close"], 30).iloc[-1] for s in crypto]))
    sr = float(ind.roc(bars["SPY"]["close"], 30).iloc[-1])
    out = {s: 0.0 for s in ALL}
    if max(cr, sr, 0.0) == 0.0:
        return out  # cash
    if cr > sr:
        out.update({s: 1 / 3 for s in crypto})
    else:
        out["SPY"] = 1.0
    return out


def p7(bars, sleeve, now):
    out = {}
    for s in ALL:
        v = votes(bars[s])
        out[s] = (sum(v.values()) / 9.0) * EW
    return out


def p8(bars, sleeve, now):
    if not _weekly(sleeve, now):
        return None
    rets = pd.DataFrame({s: bars[s]["close"].pct_change() for s in ALL}).dropna().iloc[-60:]
    if len(rets) < 30:
        return {s: EW for s in ALL}
    cov = rets.cov().values
    w = np.linalg.pinv(cov) @ np.ones(N)
    for _ in range(5):
        w = np.clip(w, 0, None)
        if w.sum() <= 0:
            w = np.ones(N)
        w = w / w.sum()
        w = np.minimum(w, 0.40)
        w = w / w.sum()
    return {s: float(w[i]) for i, s in enumerate(ALL)}


def p9(bars, sleeve, now):
    out = {s: 0.0 for s in ALL}
    wd, hr = now.weekday(), now.hour
    weekend = wd in (5, 6) or (wd == 4 and hr >= 20) or (wd == 0 and hr < 12)
    if weekend:
        out.update({"BTC/USD": 0.35, "ETH/USD": 0.35})
    dom = now.day
    if dom >= 27 or dom <= 4:  # calendar-day approximation of turn-of-month
        out["SPY"] = 0.30
    return out


def p10(bars, sleeve, now):
    spy = bars["SPY"]["close"]
    vol = ind.realized_vol(spy, 20)
    risk_on = (spy.iloc[-1] > ind.sma(spy, 200).iloc[-1]
               and vol.iloc[-1] < vol.rolling(252, min_periods=60).median().iloc[-1])
    out = {}
    for s in ALL:
        v = votes(bars[s])
        if risk_on:
            out[s] = EW * (v["v1"] + v["v4"] + v["v6"]) / 3.0
        else:
            out[s] = 0.5 * EW * (v["v2"] + v["v3"] + v["v9"]) / 3.0
    return out


REGISTRY = {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6, "S7": s7,
            "S8": s8, "S9": s9, "S10": s10, "P1": p1, "P2": p2, "P3": p3, "P4": p4,
            "P5": p5, "P6": p6, "P7": p7, "P8": p8, "P9": p9, "P10": p10}
