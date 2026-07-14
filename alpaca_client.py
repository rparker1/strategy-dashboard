"""Thin REST client for the Alpaca paper trading + data APIs. No SDK dependency."""
import json
import os
import time
import datetime as dt

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))


def _headers():
    key = os.environ.get("APCA_API_KEY_ID")
    sec = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not sec:
        # fall back to secrets file (kept out of any repo)
        p = os.path.join(HERE, "secrets.json")
        if os.path.exists(p):
            s = json.load(open(p))
            key, sec = s["key_id"], s["secret_key"]
    if not key or not sec:
        raise RuntimeError("Alpaca API keys not configured")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


def _get(url, params=None):
    for attempt in range(3):
        r = requests.get(url, headers=_headers(), params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _post(url, payload):
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text}")
    return r.json()


def _delete(url):
    r = requests.delete(url, headers=_headers(), timeout=30)
    if r.status_code >= 400 and r.status_code != 404:
        raise RuntimeError(f"DELETE {url} -> {r.status_code}: {r.text}")
    return r.json() if r.text else {}


# ---------------- account / positions / orders ----------------

def account():
    return _get(CFG["base_url"] + "/v2/account")


def positions():
    return _get(CFG["base_url"] + "/v2/positions")


def clock():
    return _get(CFG["base_url"] + "/v2/clock")


def list_orders(status="open"):
    return _get(CFG["base_url"] + "/v2/orders", params={"status": status, "limit": 500})


def cancel_all_orders():
    return _delete(CFG["base_url"] + "/v2/orders")


def submit_order(symbol, side, qty=None, notional=None, tif=None):
    is_crypto = "/" in symbol
    payload = {
        "symbol": symbol,
        "side": side,
        "type": "market",
        "time_in_force": tif or ("gtc" if is_crypto else "day"),
    }
    if notional is not None:
        payload["notional"] = str(round(abs(notional), 2))
    else:
        payload["qty"] = str(abs(qty))
    return _post(CFG["base_url"] + "/v2/orders", payload)


# ---------------- market data ----------------

def _bars_to_df(bars):
    df = pd.DataFrame(bars)
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"])
    df = df.set_index("t").rename(columns={"o": "open", "h": "high", "l": "low",
                                           "c": "close", "v": "volume"})
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def stock_bars(symbols, days=400):
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    out, page = {}, None
    while True:
        params = {"symbols": ",".join(symbols), "timeframe": "1Day",
                  "start": start, "feed": "iex", "limit": 10000, "adjustment": "split"}
        if page:
            params["page_token"] = page
        j = _get(CFG["data_url"] + "/v2/stocks/bars", params)
        for sym, bars in (j.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars)
        page = j.get("next_page_token")
        if not page:
            break
    return {s: _bars_to_df(b) for s, b in out.items()}


def crypto_bars(symbols, days=400):
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    out, page = {}, None
    while True:
        params = {"symbols": ",".join(symbols), "timeframe": "1Day",
                  "start": start, "limit": 10000}
        if page:
            params["page_token"] = page
        j = _get(CFG["data_url"] + "/v1beta3/crypto/us/bars", params)
        for sym, bars in (j.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars)
        page = j.get("next_page_token")
        if not page:
            break
    return {s: _bars_to_df(b) for s, b in out.items()}


def latest_prices(stock_symbols, crypto_symbols):
    """Latest trade price for every symbol."""
    prices = {}
    if stock_symbols:
        j = _get(CFG["data_url"] + "/v2/stocks/trades/latest",
                 {"symbols": ",".join(stock_symbols), "feed": "iex"})
        for s, t in (j.get("trades") or {}).items():
            prices[s] = float(t["p"])
    if crypto_symbols:
        j = _get(CFG["data_url"] + "/v1beta3/crypto/us/latest/trades",
                 {"symbols": ",".join(crypto_symbols)})
        for s, t in (j.get("trades") or {}).items():
            prices[s] = float(t["p"])
    return prices


def all_bars(days=400):
    bars = {}
    bars.update(stock_bars(CFG["stock_symbols"], days))
    bars.update(crypto_bars(CFG["crypto_symbols"], days))
    return bars
