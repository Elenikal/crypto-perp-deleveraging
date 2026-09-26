# Forced flow and price impact in crypto perpetual futures

How much of a crypto drawdown is information, and how much is the margin
engine selling into itself?

## Data

Hyperliquid. Public REST for candles and funding (free). S3 archive for
liquidation buckets and position-level fills (requester-pays).

**Set an AWS budget alert at $1 before any S3 call.**

## Staging

| Stage | Cost | What |
|---|---|---|
| 0 | $0 | REST candles + funding history. No AWS account needed. |
| 1 | cents | 5-min aggregated liquidation buckets from S3. |
| 2 | dollars | One day of column-pruned fills, for the margin-model gate. |

Stage 2 is conditional on 0 and 1 looking good.

## The Stage 2 gate

Take ten accounts liquidated on one day, pull their positions from the prior
day's snapshot, compute the implied liquidation price from
`MM = 1 / (2 * maxLeverage)`, and compare against the `markPx` recorded in the
fill's `liquidation` object. If the computed trigger reproduces the observed
trigger, the cascade engine rests on validated ground.

## Usage

    pip install boto3
    python3 probe.py candles --coins BTC ETH SOL --days 3 --interval 5m
    python3 probe.py funding --coins BTC ETH SOL --days 30
    python3 probe.py ls --bucket reservoir --prefix '' --dry-run

Every S3 command sums object bytes and prints the cost before transferring,
and refuses to download without `--confirm` and an explicit `--budget-mib`.

## Open questions

- Does the bulk fills schema carry `startPosition`, or is it REST-only?
- Do daily snapshots record margin mode? Cross vs isolated changes the ladder.
- Do account values include HLP vault equity?
- Does spot balance back perp margin? Believed no; confirm.
