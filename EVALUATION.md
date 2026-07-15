# PRE-REGISTERED EVALUATION CRITERIA — frozen 2026-07-14

This document was written and committed BEFORE meaningful live results existed
(day 2 of the test). Its thresholds may not be changed for the duration of the
test. `evaluate.py` implements it; if code and this document disagree, this
document wins. Changing these criteria after seeing results invalidates the
test's conclusions — that is the entire point of writing them down now.

## Evaluation date

**Monday 2026-10-12**, provided at least **60 live trading days** have
accumulated. If check-in outages reduce the live sample below 60 days, the
evaluation slips until 60 days exist. Interim runs of `evaluate.py` before that
date are diagnostics only and decide nothing.

## Procedure on evaluation day

1. `python backtest.py` — regenerate the frozen-rules backtest so its window
   covers the live quarter.
2. `python evaluate.py` — produces the report.
3. Decisions follow the criteria below mechanically. Judgment is allowed only
   where the criteria are silent.

## What CAN be decided (and the thresholds)

- **KILL-COST.** A sleeve whose backtest-measured fee+slippage drag exceeds
  **3% of capital per year** is retired. No plausible edge at this scale
  survives that cost. (Known at registration time: P9 is at ~14%/yr in the
  baseline backtest and is expected to fail this test; it stays in the live
  test anyway as the falsifiable control it was designed to be.)
- **KILL-REDUNDANT.** Two sleeves with backtest daily-return correlation
  **> 0.90** (live-confirmed > 0.80 where 30+ shared days exist) are one
  strategy wearing two names: retire the one with the higher live turnover.
- **REVIEW-DEFECT.** A sleeve whose live daily returns correlate **< 0.60**
  with its own backtest over the shared window is not implementing its spec —
  that is a bug hunt, not a performance judgment. Fix-and-continue or retire,
  but the diagnosis must be written in the journal.
- **FAMILY TILT.** Capital may shift between strategy families (trend /
  reversion / allocation / relative-value / meta) by at most **±20%**,
  informed by pooled family Sharpes. Never sleeve-by-sleeve based on ranking.
- **CONTINUE.** Everything else continues unchanged into the next quarter with
  survivors' capital rebased.

## What CANNOT be decided at day 90

- **No parameter changes to a live strategy, ever.** A "tweak" (S1's 20/50 →
  15/40, different z-score bands, etc.) creates a NEW sleeve (e.g. `S1b`)
  which starts from scratch alongside the incumbent. Incumbents are never
  edited — edited strategies have no track record.
- **No kills for losing.** A sleeve that loses money while matching its
  backtest behavior and paying reasonable costs is doing its job in a hostile
  regime. One quarter cannot distinguish an unlucky good strategy from a bad
  one (Sharpe standard error over 63 days ≈ ±2 annualized).
- **No promotion of the "winner."** The best live performer at day 90 is,
  with high probability, mostly noise. It earns continuation, not extra capital
  beyond the family-tilt cap.

## Statistical honesty requirements for the report

- Every live Sharpe is reported **with a bootstrap 95% CI** (circular block,
  block = 5, n = 2000). Rankings without error bars are not shown.
- The backtest is labeled for what it is: the same frozen rules over ~9 months
  of history through a specific (crypto-bear) regime — quasi-out-of-sample
  because these are textbook strategies not fitted to this data, but a single
  regime nonetheless.
- The report states the live sample size in its header and refuses a "valid"
  stamp below 60 live days.

## Baseline expectations (registered 2026-07-14, backtest 2025-10-10 → 2026-07-13)

So that day-90 claims of "surprise" can be checked against what we already
knew: the backtest regime was a crypto bear (S10 buy-and-hold −29%). Positive
sleeves were the mean-reverters S2 (+5.1%) and S9 (+2.3%) and the pairs trade
P5 (+8.9%). P4 (−38%) is structurally long a crashing asset class. P9's fee
drag (~14%/yr) makes it a registered expected failure. P7 must beat the
average of S1–S9 to justify its existence; in the baseline it does not.
