"""Offline smoke test: synthetic bars, dry+live simulated runs, no network."""
import datetime as dt

import numpy as np
import pandas as pd

import datastore
import engine

rng = np.random.default_rng(7)


def fake_df(days=420, start_price=100.0, drift=0.0004, vol=0.02):
    idx = pd.date_range(end=dt.date.today(), periods=days, freq="D")
    r = rng.normal(drift, vol, days)
    close = start_price * np.exp(np.cumsum(r))
    high = close * (1 + np.abs(rng.normal(0, 0.008, days)))
    low = close * (1 - np.abs(rng.normal(0, 0.008, days)))
    open_ = np.roll(close, 1); open_[0] = start_price
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": rng.uniform(1e6, 5e6, days)}, index=idx)


BARS = {s: fake_df(start_price=p, vol=v) for s, p, v in [
    ("SPY", 600, 0.010), ("NVDA", 180, 0.028), ("AAPL", 260, 0.016), ("MSFT", 510, 0.015),
    ("BTC/USD", 110000, 0.030), ("ETH/USD", 4000, 0.038), ("SOL/USD", 200, 0.05)]}
PRICES = {s: float(df["close"].iloc[-1]) for s, df in BARS.items()}

datastore.load_bars = lambda: BARS
datastore.latest_prices = lambda: (PRICES, "synthetic")

print("dry :", engine.run(dry=True))
print("live:", engine.run(dry=False))
print("rep :", engine.run(dry=False))  # idempotency: should be ~0 decisions

import json
state = json.load(open(engine.STATE_PATH))
total = 0
for sid, sv in state["sleeves"].items():
    eq = engine.sleeve_equity(sv, PRICES)
    total += eq
    assert 2000 < eq < 8000, f"{sid} equity insane: {eq}"
print(f"total=${total:,.2f}  fees=${state['fees_paid']:.2f}")
assert 99000 < total <= 100000, "total drifted"
print("OK")
