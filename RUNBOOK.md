# CHECK-IN RUNBOOK — Strategy Test (simulator mode)

You are running a twice-daily check-in for a 20-strategy paper-trading test.
Everything lives in `/home/claude/work/trading/`. The user reviews from their
phone; you decide autonomously within the rules below.

## 0. Restore if the container is fresh (CHECK FIRST)

Containers are ephemeral — the project may not exist on disk. If
`/home/claude/work/trading/engine.py` is missing:

    git clone https://x-access-token:<GITHUB_TOKEN>@github.com/rossparker-jp-engineers/strategy-dashboard.git /home/claude/work/trading

(The token is in your task prompt.) Then recreate
`/home/claude/work/trading/secrets.json` from the credentials in your task
prompt (it is .gitignored, never in the repo). The clone contains code,
runbook, all market data CSVs, state, and journal — the test resumes exactly
where it left off. NEVER rebuild the project from scratch or from memory; if
the clone fails, notify the user and stop.

## 1. Refresh market data

**Crypto (Kraken — ALWAYS use OHLC endpoint, NEVER the Ticker endpoint; the
Ticker serves stale cached pages through this fetch route):**

For each pair, WebFetch (prompt: "Output ONLY the raw JSON response, complete
and untruncated, no commentary, no markdown fences."):

- `https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since=<UNIX_10_DAYS_AGO>`
- same with `pair=ETHUSD` and `pair=SOLUSD`

Save each response body to `data/raw/<pair>.txt` (if the tool persisted the
output to a file, `cp` that file instead of retyping). Then:

    python datastore.py ingest-kraken data/raw/xbt.txt BTC/USD
    python datastore.py ingest-kraken data/raw/eth.txt ETH/USD
    python datastore.py ingest-kraken data/raw/sol.txt SOL/USD

The LAST row of each OHLC payload is today's incomplete bar — its close is the
live price. Collect those three closes for step 2.

**Stocks (Alpha Vantage — key in `secrets.json` under `alphavantage_key`;
free tier 25 requests/day, do not exceed 12 per check-in):**

Evening run (after US close) — refresh daily history for each of SPY, NVDA,
AAPL, MSFT:

- `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=SPY&outputsize=compact&apikey=<KEY>`

Save to `data/raw/<sym>.txt`, then `python datastore.py ingest-av data/raw/spy.txt SPY` etc.

Morning run (US market closed) — skip stock fetches entirely; last close is
correct and saves API quota. Optionally fetch GLOBAL_QUOTE per symbol if a
live-ish price matters:

- `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=<KEY>` → price field `05. price`

## 2. Update latest quotes

Write a JSON dict of every price you have to `/tmp/q.json` and run:

    python datastore.py ingest-quotes /tmp/q.json

Format: `{"BTC/USD": 62151.2, "ETH/USD": 1763.82, "SOL/USD": 74.55, "SPY": 623.4, ...}`
Symbols you omit fall back to last close automatically. The ingest rejects
any quote >50% away from last close — if that fires, your data is corrupt;
re-fetch rather than override.

## 3. Run the engine

    python datastore.py check        # data sanity — investigate anything flagged
    python engine.py run             # computes signals, fills, journals, rebuilds dashboard

## 4. Strategic review (your decisions, autonomous)

Read the run output flags and `state/journal.jsonl` tail. Rules of engagement:

- **Flattened sleeve (15% DD breach):** investigate why. If the loss came from
  a coherent signal doing its job in a bad market, re-enable after 5 trading
  days (`flattened: false` in state/state.json). If it came from a bug or
  runaway churn, keep it flat and note the diagnosis in the journal.
- **Kill switch (20% account DD):** everything stays flat; notify the user and
  wait for their input. Do NOT restart on your own.
- **DO NOT tune strategy parameters mid-test.** The test is only valid if
  rules stay fixed. Log improvement ideas in `state/ideas.md` for the
  60-day review instead.
- **Broken behavior** (strategy error flags, absurd turnover, data staleness)
  may be fixed in code — that's infrastructure repair, not parameter tuning.
  Journal what you changed and why.
- **Record every strategic decision and review in the journal** so it appears
  in the user's PWA check-in history:
      python engine.py note decision "Kept S4 frozen: churn came from a data gap, not the signal"
      python engine.py note review "Weekly review: ..."
  Anything you decide (re-enabling a sleeve, keeping one frozen, diagnosing a
  flag, notable observations) gets a `decision` note. Do this BEFORE publish.
- Weekly (Monday evening run): write the comparative review as a `review` note
  — best/worst sleeves, ensemble (P7) vs its members, anything approaching a
  risk limit.

## 5. Publish & report

- `python publish.py` — commits and pushes the ENTIRE project (code, data,
  state, journal, dashboard PWA) to GitHub. This is the durability layer:
  if this push fails, the run's results exist only on this ephemeral
  container, so treat a failure as urgent — retry once, then tell the user.
- SendUserFile `dashboard.html` (display: render) with a 1-line caption:
  total return, best sleeve, worst sleeve, any flags.
- Only message beyond that if something needs the user's eyes (kill switch,
  repeated data failures, a sleeve you chose to keep flat).

## Known data hazards (learned the hard way)

- Kraken **Ticker** endpoint returns months-stale cached data via this fetch
  route. OHLC endpoint is verified good. Use OHLC only.
- Large fetch payloads get truncated mid-JSON. The Kraken ingester is
  row-based regex and tolerates this; losing the newest rows is possible, so
  check `datastore.py check` ages after ingest.
- Payloads pass through a summarizer model — digit corruption is possible.
  The validators (monotonic dates, >0 prices, <60% daily moves, <50% quote
  jumps) exist for this reason. Never bypass them. If in doubt, re-fetch with
  a narrow `since` and compare overlapping rows.
- Alpha Vantage rate limit message ("Information": ...) instead of data means
  quota exhausted — skip stocks this run, use last closes, note it in journal.
