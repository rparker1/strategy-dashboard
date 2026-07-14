"""Technical indicators on pandas Series/DataFrames of daily bars.
All functions take a DataFrame with columns: open, high, low, close, volume (index = date).
"""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std()
    return mid - k * sd, mid, mid + k * sd  # lower, mid, upper


def keltner(df: pd.DataFrame, n: int = 20, k: float = 1.5):
    mid = ema(df["close"], n)
    a = atr(df, n)
    return mid - k * a, mid, mid + k * a


def macd(close: pd.Series, fast=12, slow=26, sig=9):
    line = ema(close, fast) - ema(close, slow)
    signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal


def roc(close: pd.Series, n: int) -> pd.Series:
    return close.pct_change(n)


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    """Annualized realized vol from daily log returns."""
    r = np.log(close / close.shift())
    return r.rolling(n).std() * np.sqrt(365)
