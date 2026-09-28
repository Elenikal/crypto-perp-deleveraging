# Leverage Before the Crash

When a crypto market falls hard, how much of it is the margin engine rather than
the news? Open interest destroyed during the fall is the trace forced selling
leaves behind.

Live results page: published as a Claude artifact (`paper.html` + `results.json`).

## Findings

| | Result | Evidence |
|---|---|---|
| **Robust** | Leverage built up before a shock predicts how much is liquidated in it | b = -2.79 (t = -5.2); holds in all 5 markets, both sample halves, with FE and depth controlled |
| **Fragile** | The same leverage predicts a deeper fall | b = -0.73 (t = -2.8) pooled, weakens in both halves |
| **Not found** | A mechanical overshoot that reverses | two-hour gap +0.40pp (t = 1.8), gone as a continuous relationship |

## Two measurement results

Both cost real time to discover, so they are recorded here.

- At **5-minute** frequency the open-interest proxy is noise: near-zero correlation
  with returns, and in the worst bars open interest is as likely to rise as fall.
  At **hourly** frequency the same proxy correlates +0.66 to +0.76. Hence hourly.
- **OI divided by volume**, the obvious leverage measure, correlates **-0.87 with
  volume**. It measures how quiet a market is, not how levered. Leverage is
  therefore open interest against its own trailing 30-day mean.

## Data

Binance USD-M perpetuals from `data.binance.vision`: free, public, no account and
no credentials. 5 markets, Oct 2024 to Aug 2026, hourly, about 240 MB.

Binance's live API is geo-blocked (HTTP 451) from most locations, so the live
strip on the results page uses Hyperliquid instead, labelled as context rather
than sample.

## Method

An episode is the worst 2% of 6-hour drawdowns per market, thinned to one per 24
hours. Event time zero is the end of the drawdown window, so no trough is picked
with hindsight. Standard errors are clustered by calendar day: 437 episodes come
from only 170 days, and these markets fall together.

## Reproduce

    ./run.sh

That is the whole thing: it creates `.venv`, installs numpy and pandas, downloads
about 240 MB of free public files (cached, so re-runs skip them), and writes
`results.json`.

`fetch.py` uses only the standard library and runs under any `python3`.
`analyze.py` needs numpy and pandas, so run it as `.venv/bin/python analyze.py`
if you are not using `run.sh`.

`probe.py` is an earlier exploratory tool: free Hyperliquid and Binance pulls,
plus requester-pays S3 listing with cost guards. Not needed for the study above.
`monitor.html` is a separate live leverage dashboard.

## Deploy

The page is published by GitHub Pages and rebuilt by GitHub Actions
(`.github/workflows/deploy.yml`). The workflow re-downloads any new days, re-runs
the analysis and redeploys, on every push to `main` and every Monday at 06:00 UTC.
It can also be run by hand from the Actions tab.

Published paths:

| path | page |
|---|---|
| `/` | the study, `paper.html` |
| `/monitor.html` | the live venue readout |
| `/results.json` | the numbers behind the page |

One-time setup after the first push: **Settings > Pages > Source > GitHub Actions**.
Nothing else, and no secrets: every data source is public and unauthenticated.

`fetch.py` tracks up to two days ago by default, using monthly Binance files for
complete months and daily files for the month in progress. Set `END_DATE` to pin
it to a fixed day.

## Limits

Forced flow is proxied, not observed: true liquidation records sit behind a paid
feed. Five markets, one venue, two years.
