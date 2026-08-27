
## 2026-07-20 (week-1 review)
- P7 ensemble is flat (-0.11%) while its member sleeves average solidly positive: its many small rebalances generate steady fees without capturing member trends. Idea for day-90: evaluate a rebalance deadband / min-trade-notional for ensembles to cut fee drag. (Observation only — no live change.)
- P9 round-tripped BTC+ETH in one trading day (~$17.7 fees on $3.5k notional), consistent with its pre-registered expected cost-kill. Tracking as evidence for the day-90 cost analysis.

## 2026-08-18 (evening)
- **Quote file path is unsafe.** `ingest-quotes` is documented to read `/tmp/q.json`. `/tmp` is world-writable and shared; today a leftover file from an unrelated process was ingested after our own write failed. Move the runbook's quote path into the project root (`q.json`, gitignored) and have `ingest_quotes` reject any file whose mtime is older than the current run's start.
- **Alpha Vantage `outputsize=full` is now premium-only.** The runbook's documented staleness workaround no longer exists on the free tier. Need a replacement for the stale-cache hazard — candidates: a second free provider for cross-check, or accepting last-close carry with an explicit staleness flag surfaced on the dashboard.
- **Dashboard should surface per-symbol data age.** Today MSFT was two trading days stale and SOL one day, but nothing on the dashboard would tell the user that. A per-symbol "as of" badge would make partial-refresh runs auditable at a glance.
- **Check-in continuity monitoring.** A 20-day outage passed unnoticed. Worth a heartbeat check that alerts if no `run` record has been journalled in over 24 hours.

## 2026-08-19 (morning)
- **Default the Kraken fetch to `since=1`, not the bare OHLC URL.** This morning the bare `OHLC?pair=...&interval=1440` URL served a day-stale cached snapshot for BTC and ETH; `&since=1` returned current data for ETH from the same route seconds later. SOL happened to be fresh on the bare URL, so the staleness is per-cache-key rather than per-endpoint. Runbook change candidate: fetch `since=1` first, and treat a payload whose `last` field is more than one interval behind the container clock as stale regardless of how recent the newest row looks.
- **Validate freshness on the payload's `last` field, not the newest row.** The newest row is always the incomplete bar, so "newest row is yesterday" reads as acceptable even when the response is a full day behind. Comparing `last` to the expected last committed interval catches it immediately, and would have caught this run's BTC problem without the accidental corroboration from yesterday's journal.
- **The fetch route de-duplicates identical URLs for up to an hour.** Once a stale payload has been received, the same URL cannot be retried within the run, so there must be more than one distinct cache-bust URL per symbol available (e.g. varying `since` to a real recent epoch) or a stale fetch is unrecoverable for that check-in. This is what left BTC unrepairable today.

## 2026-08-25 (morning) — infrastructure, for the 60-day review
- Fetch-route freshness is non-deterministic per URL variant. Both the plain
  Kraken OHLC URL and the `since=1` cache-bust variant can return a stale
  cached payload, and which one is fresher differs by pair on the same run
  (25 Aug: plain was fresher for ETH, since=1 fresher for BTC). Consider making
  the runbook mandate fetching both and selecting on newest bar timestamp,
  rather than preferring either.
- Missed check-ins leave a silent data gap. Five days elapsed between the
  20 Aug morning run and 25 Aug with no journal entry. A staleness age is
  reported by `datastore.py check`, but nothing distinguishes "market closed"
  from "no run happened". Worth a heartbeat/last-run-age line on the dashboard.
- Equity daily bars can only be refreshed by TIME_SERIES_DAILY. When that URL
  is unavailable to a run, the stock leg trades on short windows with only a
  flag to show for it. Consider whether the engine should skip or freeze
  stock-side sleeves when their history exceeds a staleness threshold, instead
  of trading and flagging. NOT a parameter change — a data-integrity gate.

## 2026-08-26 (evening)
- **Alpha Vantage `outputsize=full` is no longer a usable cache-bust.** The endpoint
  now rejects it as premium-only for TIME_SERIES_DAILY, which removes the fallback
  the runbook and the check-in prompt both rely on. MSFT went unrefreshed for a
  second consecutive check-in as a result. For the 60-day review: either source
  equity bars from a provider that does not sit behind this cache, or add a
  documented secondary URL form that is known to miss the cache.
- **Stale-symbol marking policy.** `latest.json` can carry a quote forward
  indefinitely with no link to any bar (MSFT sat at 481.63 for days against a last
  close of 495.40). Consider having `ingest-quotes` expire any quote older than N
  days back to the last close automatically, rather than leaving it to the operator
  to spot.
- **Kraken first-fetch staleness is now confirmed intermittent per pair**, not just
  per endpoint: ETH returned a cached incomplete bar while BTC and SOL were current
  in the same batch. A cheap defence is to always fetch the `since=1` variant for
  every pair rather than only on suspicion.
All three are data-integrity items. No strategy parameters touched.

## 2026-08-27 (evening)
- **Correction to the 26 Aug Kraken recommendation.** Yesterday's note suggested
  always preferring the `since=1` variant. Today that would have poisoned two of
  three pairs: `since=1` served a stale cache for ETH (newest bar 26 Aug, an
  incomplete 2462.21 vs the settled 2507.08) and a badly stale one for SOL (newest
  bar 20 Aug, seven days behind), while the plain OHLC URL was current for both.
  BTC was current on both variants. Conclusion: neither URL form is reliably
  fresher — the only safe rule is to fetch BOTH forms and take the payload whose
  newest bar is latest, comparing overlapping rows. Cheap: the ingester is
  row-based and tolerant. For the 60-day review, this belongs in the runbook as a
  fetch-and-compare step rather than a fetch-then-suspect step.
- **Cache-bust URLs are no longer constructible by the check-in session.** The
  fetch tooling now only permits URLs that appeared verbatim in the task prompt or
  in a prior fetch result, so the runbook's `&cb=<YYYYMMDD><am|pm>` trick cannot be
  used, and neither can arbitrary `since=` windows. Parameter reordering does not
  help either — the fetcher normalises and de-duplicates on the canonical URL. Any
  cache-bust variant we want available must be written into the scheduled-task
  prompt in advance. This is the root cause of every unresolved staleness this week.
- **Alpha Vantage publication lag is per-symbol, not a cache artefact.** At 20:26
  UTC today MSFT returned a settled 27 Aug bar while SPY, NVDA and AAPL all
  returned 26 Aug from the same route in the same batch. That is AV's own
  publication order, not the fetch cache — so an evening run at ~20:25 UTC is
  simply too early for most symbols. Consider moving the evening check-in ~60-90
  minutes later, or accepting a one-day-lagged equity leg by design.
All data-integrity / scheduling items. No strategy parameters touched.
