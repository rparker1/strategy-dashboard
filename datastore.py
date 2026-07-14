"""File-based market data store for simulator mode.

Bars live in data/<SYM>.csv (date,open,high,low,close,volume; SYM has / stripped).
Latest prices live in data/latest.json  {"SPY": 623.1, "BTC/USD": 77480.0, ...,
                                          "_ts": "<iso>"}.

Raw WebFetch payloads are saved by the assistant into data/raw/, then ingested:
    python datastore.py ingest-kraken  data/raw/xbt.txt  BTC/USD
    python datastore.py ingest-av      data/raw/spy.txt  SPY
    python datastore.py ingest-quotes  data/raw/quotes.txt
    python datastore.py check
Parsers are tolerant of markdown fences and surrounding prose; every ingest is
validated (monotonic dates, positive prices, |daily move| < 60%) before merge.
"""
import datetime as dt
import json
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CFG = json.load(open(os.path.join(HERE, "config.json")))
ALL = CFG["stock_symbols"] + CFG["crypto_symbols"]

KRAKEN_KEYS = {"BTC/USD": ["XXBTZUSD", "XBTUSD"], "ETH/USD": ["XETHZUSD", "ETHUSD"],
               "SOL/USD": ["SOLUSD"]}


def _path(sym):
    return os.path.join(DATA, sym.replace("/", "") + ".csv")


def _extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object found in payload")
    return json.loads(m.group(0))


def _validate(df, sym):
    assert not df.empty, f"{sym}: empty frame"
    assert df.index.is_monotonic_increasing, f"{sym}: dates not sorted"
    assert (df[["open", "high", "low", "close"]] > 0).all().all(), f"{sym}: nonpositive price"
    moves = df["close"].pct_change().abs().dropna()
    assert (moves < 0.60).all(), f"{sym}: implausible daily move {moves.max():.0%}"
    return df


def _merge(sym, new_df):
    os.makedirs(DATA, exist_ok=True)
    p = _path(sym)
    if os.path.exists(p):
        old = pd.read_csv(p, index_col=0, parse_dates=True)
        new_df = pd.concat([old, new_df])
        new_df = new_df[~new_df.index.duplicated(keep="last")].sort_index()
    _validate(new_df, sym)
    new_df.to_csv(p)
    return len(new_df)


def ingest_kraken(raw_path, sym):
    # Row-based regex parse: tolerates payloads truncated mid-JSON by the fetcher.
    text = open(raw_path).read()
    pat = re.compile(r'\[(\d{10}),"([\d.]+)","([\d.]+)","([\d.]+)","([\d.]+)",'
                     r'"([\d.]+)","([\d.]+)",(\d+)\]')
    rows = [m.groups() for m in pat.finditer(text)]
    if len(rows) < 50:
        raise ValueError(f"only {len(rows)} complete OHLC rows found for {sym}")
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close",
                                     "vwap", "volume", "count"])
    df.index = pd.DatetimeIndex(pd.to_datetime(df["t"].astype(int), unit="s")).normalize()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df.iloc[:-1] if len(df) > 1 else df  # drop today's incomplete bar
    n = _merge(sym, df)
    print(f"{sym}: merged, {n} bars total")


def ingest_av(raw_path, sym):
    # Row-based regex parse: tolerates payloads truncated mid-JSON by the fetcher.
    text = open(raw_path).read()
    if '"Information"' in text and "Time Series" not in text:
        raise ValueError(f"AV rate-limit/notice payload for {sym}, no data")
    pat = re.compile(
        r'"(\d{4}-\d{2}-\d{2})":\s*\{\s*"1\. open":\s*"([\d.]+)",\s*"2\. high":\s*"([\d.]+)",'
        r'\s*"3\. low":\s*"([\d.]+)",\s*"4\. close":\s*"([\d.]+)",\s*"5\. volume":\s*"(\d+)"\s*\}',
        re.DOTALL)
    rows = pat.findall(text)
    if len(rows) < 5:  # fall back to CSV-style lines: date,o,h,l,c,volume
        csv_pat = re.compile(r'(\d{4}-\d{2}-\d{2}),([\d.]+),([\d.]+),([\d.]+),([\d.]+),(\d+)')
        rows = csv_pat.findall(text)
    if len(rows) < 5:
        raise ValueError(f"only {len(rows)} complete daily rows found for {sym}")
    recs = {pd.Timestamp(d): {"open": float(o), "high": float(h), "low": float(l),
                              "close": float(c), "volume": float(v)}
            for d, o, h, l, c, v in rows}
    df = pd.DataFrame.from_dict(recs, orient="index").sort_index()
    n = _merge(sym, df)
    print(f"{sym}: merged {len(df)} parsed rows, {n} bars total")


def ingest_weekly_closes(csv_path, sym):
    """Backfill synthetic daily bars from weekly closes (date,close CSV), ONLY
    for dates strictly before existing daily coverage. Used because AV's full
    daily history is premium; weekly is free. Synthetic bars have o=h=l=c and
    only feed long lookbacks (SMA200, vol median) — short-window indicators
    always operate on real daily bars."""
    wk = pd.read_csv(csv_path, index_col=0, parse_dates=True).sort_index()
    daily = pd.Series(wk["close"].values, index=wk.index).resample("B").ffill()
    p = _path(sym)
    if os.path.exists(p):
        cutoff = pd.read_csv(p, index_col=0, parse_dates=True).index.min()
        daily = daily[daily.index < cutoff]
    if daily.empty:
        print(f"{sym}: nothing to backfill")
        return
    df = pd.DataFrame({"open": daily, "high": daily, "low": daily,
                       "close": daily, "volume": 0.0})
    n = _merge(sym, df)
    print(f"{sym}: backfilled {len(df)} synthetic days, {n} bars total")


def ingest_quotes(raw_path):
    """Latest prices from a JSON dict {'SPY': 623.4, 'BTC/USD': 77000, ...}."""
    j = _extract_json(open(raw_path).read())
    p = os.path.join(DATA, "latest.json")
    cur = json.load(open(p)) if os.path.exists(p) else {}
    for k, v in j.items():
        assert k in ALL, f"unknown symbol {k}"
        v = float(v)
        assert v > 0, f"bad price {k}={v}"
        hist = load_bars().get(k)
        if hist is not None and not hist.empty:
            ref = hist["close"].iloc[-1]
            assert abs(v / ref - 1) < 0.5, f"{k} quote {v} vs last close {ref}: >50% jump"
        cur[k] = v
    cur["_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    json.dump(cur, open(p, "w"), indent=1)
    print("latest:", {k: v for k, v in cur.items() if k != '_ts'})


def load_bars():
    out = {}
    for s in ALL:
        p = _path(s)
        if os.path.exists(p):
            out[s] = pd.read_csv(p, index_col=0, parse_dates=True)
    return out


def latest_prices():
    p = os.path.join(DATA, "latest.json")
    prices, ts = {}, None
    if os.path.exists(p):
        j = json.load(open(p))
        ts = j.pop("_ts", None)
        prices = {k: float(v) for k, v in j.items()}
    bars = load_bars()
    for s in ALL:  # fall back to last close
        if s not in prices and s in bars and not bars[s].empty:
            prices[s] = float(bars[s]["close"].iloc[-1])
    return prices, ts


def check():
    bars = load_bars()
    prices, ts = latest_prices()
    ok = True
    for s in ALL:
        if s not in bars or bars[s].empty:
            print(f"MISSING history: {s}")
            ok = False
            continue
        age = (pd.Timestamp.now() - bars[s].index[-1]).days
        print(f"{s:>8}: {len(bars[s]):4d} bars, last {bars[s].index[-1].date()} "
              f"({age}d old), latest px {prices.get(s)}")
        if len(bars[s]) < 260:
            print(f"   WARNING: {s} has <260 bars; long lookbacks degraded")
    print("quote timestamp:", ts)
    return ok


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "ingest-kraken":
        ingest_kraken(sys.argv[2], sys.argv[3])
    elif cmd == "ingest-av":
        ingest_av(sys.argv[2], sys.argv[3])
    elif cmd == "ingest-weekly":
        ingest_weekly_closes(sys.argv[2], sys.argv[3])
    elif cmd == "ingest-quotes":
        ingest_quotes(sys.argv[2])
    elif cmd == "check":
        sys.exit(0 if check() else 1)
