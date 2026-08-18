
## 2026-07-20 (week-1 review)
- P7 ensemble is flat (-0.11%) while its member sleeves average solidly positive: its many small rebalances generate steady fees without capturing member trends. Idea for day-90: evaluate a rebalance deadband / min-trade-notional for ensembles to cut fee drag. (Observation only — no live change.)
- P9 round-tripped BTC+ETH in one trading day (~$17.7 fees on $3.5k notional), consistent with its pre-registered expected cost-kill. Tracking as evidence for the day-90 cost analysis.

## 2026-08-18 (evening)
- **Quote file path is unsafe.** `ingest-quotes` is documented to read `/tmp/q.json`. `/tmp` is world-writable and shared; today a leftover file from an unrelated process was ingested after our own write failed. Move the runbook's quote path into the project root (`q.json`, gitignored) and have `ingest_quotes` reject any file whose mtime is older than the current run's start.
- **Alpha Vantage `outputsize=full` is now premium-only.** The runbook's documented staleness workaround no longer exists on the free tier. Need a replacement for the stale-cache hazard — candidates: a second free provider for cross-check, or accepting last-close carry with an explicit staleness flag surfaced on the dashboard.
- **Dashboard should surface per-symbol data age.** Today MSFT was two trading days stale and SOL one day, but nothing on the dashboard would tell the user that. A per-symbol "as of" badge would make partial-refresh runs auditable at a glance.
- **Check-in continuity monitoring.** A 20-day outage passed unnoticed. Worth a heartbeat check that alerts if no `run` record has been journalled in over 24 hours.
