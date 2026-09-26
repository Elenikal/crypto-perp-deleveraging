#!/usr/bin/env python3
"""
Hyperliquid data probe. Costs nothing to run in --dry-run mode.

Stage 0  free:      REST candles + funding history (no AWS, no card)
Stage 1  ~cents:    aggregated 5-min liquidation buckets from S3 (small files)
Stage 2  ~dollars:  one day of fills, column-pruned, for the margin-model gate

Every S3 step lists and sums object bytes BEFORE transferring anything and
refuses to download unless you pass --confirm with a byte budget.

  python probe.py candles --coins BTC ETH SOL
  python probe.py ls-liq  --dry-run
  python probe.py ls-liq  --confirm --budget-mib 200
  python probe.py ls-fills --date 2025-10-10 --dry-run
"""
import argparse, json, os, sys, time
import urllib.request

INFO = "https://api.hyperliquid.xyz/info"
EGRESS_USD_PER_GIB = 0.09  # internet egress; $0 if you run in-region on EC2

# Verify these on first `ls-*` run. Layout is from docs, not yet confirmed by me.
BUCKETS = {
    "node":      ("hl-mainnet-node-data", ""),
    "reservoir": ("hydromancer-reservoir", ""),
}


def post(body):
    req = urllib.request.Request(
        INFO, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cmd_candles(a):
    """Free. No AWS. Builds the price side of the Stage 0 panel."""
    out = {}
    for coin in a.coins:
        end = int(time.time() * 1000)
        start = end - a.days * 86_400_000
        # candleSnapshot caps at 5000 bars per request; 1m over 3 days is ~4320
        rows = post({"type": "candleSnapshot",
                     "req": {"coin": coin, "interval": a.interval,
                             "startTime": start, "endTime": end}})
        out[coin] = len(rows)
        print(f"{coin:6s} {len(rows):6d} bars  "
              f"{rows[0]['t'] if rows else '-'} .. {rows[-1]['t'] if rows else '-'}")
        time.sleep(0.2)
    print("\nNOTE: 5000-bar cap per request. Page backwards on startTime for history.")
    return out


def cmd_funding(a):
    """Free. Funding history is the cheapest stress proxy you have."""
    for coin in a.coins:
        end = int(time.time() * 1000)
        start = end - a.days * 86_400_000
        rows = post({"type": "fundingHistory", "coin": coin,
                     "startTime": start, "endTime": end})
        prem = [float(r["premium"]) for r in rows] or [0.0]
        print(f"{coin:6s} {len(rows):5d} pts  premium min {min(prem):+.5f} "
              f"max {max(prem):+.5f}")
        time.sleep(0.2)


def s3_client(region):
    try:
        import boto3
    except ImportError:
        sys.exit("pip install boto3")
    return boto3.client("s3", region_name=region)


def listing(a, prefix):
    """List + sum bytes. Transfers metadata only, costs ~nothing."""
    bucket, base = BUCKETS[a.bucket]
    s3 = s3_client(a.region)
    tot, n, sample = 0, 0, []
    tok = None
    while True:
        kw = dict(Bucket=bucket, Prefix=base + prefix,
                  RequestPayer="requester", MaxKeys=1000)
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            tot += o["Size"]; n += 1
            if len(sample) < 8:
                sample.append((o["Key"], o["Size"]))
        if not r.get("IsTruncated"):
            break
        tok = r["NextContinuationToken"]

    gib = tot / 2**30
    print(f"bucket s3://{bucket}/{base + prefix}")
    print(f"objects {n}   total {gib:.3f} GiB")
    print(f"egress to laptop ~${gib * EGRESS_USD_PER_GIB:.2f}   "
          f"same-region EC2 $0.00 + ~${n * 4e-7:.4f} in GETs")
    for k, sz in sample:
        print(f"  {sz/2**20:9.2f} MiB  {k}")
    if n == 0:
        print("\nEMPTY. The prefix is wrong. Re-run with --prefix '' to see the "
              "real top-level layout before guessing again.")
    return n, tot


def cmd_ls(a):
    n, tot = listing(a, a.prefix)
    if not a.confirm:
        print("\nDry run. Nothing transferred. Add --confirm --budget-mib N to pull.")
        return
    mib = tot / 2**20
    if mib > a.budget_mib:
        sys.exit(f"\nREFUSED: {mib:.1f} MiB exceeds budget {a.budget_mib} MiB.")
    bucket, base = BUCKETS[a.bucket]
    s3 = s3_client(a.region)
    os.makedirs(a.out, exist_ok=True)
    tok = None
    while True:
        kw = dict(Bucket=bucket, Prefix=base + a.prefix,
                  RequestPayer="requester", MaxKeys=1000)
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            dst = os.path.join(a.out, o["Key"].replace("/", "__"))
            if os.path.exists(dst):
                continue
            s3.download_file(bucket, o["Key"], dst,
                             ExtraArgs={"RequestPayer": "requester"})
            print("got", dst)
        if not r.get("IsTruncated"):
            break
        tok = r["NextContinuationToken"]


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("candles", "funding"):
        q = sub.add_parser(name)
        q.add_argument("--coins", nargs="+", default=["BTC", "ETH", "SOL"])
        q.add_argument("--days", type=int, default=3)
        q.add_argument("--interval", default="1m")

    for name in ("ls-liq", "ls-fills", "ls"):
        q = sub.add_parser(name)
        q.add_argument("--bucket", choices=list(BUCKETS), default="reservoir")
        q.add_argument("--region", default="us-east-1")
        q.add_argument("--prefix", default="")
        q.add_argument("--date", default=None)
        q.add_argument("--dry-run", action="store_true")
        q.add_argument("--confirm", action="store_true")
        q.add_argument("--budget-mib", type=float, default=50.0)
        q.add_argument("--out", default="./raw")

    a = p.parse_args()
    if a.cmd == "candles":
        cmd_candles(a)
    elif a.cmd == "funding":
        cmd_funding(a)
    else:
        if a.date and not a.prefix:
            a.prefix = a.date
        cmd_ls(a)


if __name__ == "__main__":
    main()
