#!/usr/bin/env python3
"""
Data probe for the perp liquidation cascade project. Run from the repo dir.

  python3 probe.py funding  --coins BTC ETH SOL --days 30     # free
  python3 probe.py candles  --coins BTC --days 3 --interval 1m # free, rolling window only
  python3 probe.py binance  --date 2025-10-10                  # free, reaches history
  python3 probe.py ls --bucket reservoir --prefix '' --dry-run # requester-pays, priced first
"""
import argparse, io, json, os, sys, time, urllib.request, zipfile

INFO = "https://api.hyperliquid.xyz/info"
BINANCE = "https://data.binance.vision/data/futures/um/daily"
EGRESS_USD_PER_GIB = 0.09
BUCKETS = {"node": ("hl-mainnet-node-data", ""),
           "reservoir": ("hydromancer-reservoir", "")}
IV_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def post(body):
    req = urllib.request.Request(INFO, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- Hyperliquid
def cmd_funding(a):
    """Hourly funding. Paginated: the endpoint caps at 500 and truncates silently."""
    end = int(time.time() * 1000)
    start, expect = end - a.days * 86_400_000, a.days * 24
    for coin in a.coins:
        rows, cursor, seen = [], start, set()
        while cursor < end:
            batch = post({"type": "fundingHistory", "coin": coin,
                          "startTime": cursor, "endTime": end})
            if not batch:
                break
            for r in batch:
                if int(r["time"]) not in seen:
                    seen.add(int(r["time"])); rows.append(r)
            last = int(batch[-1]["time"])
            if last <= cursor or len(batch) < 500:
                break
            cursor = last + 1
            time.sleep(0.25)
        prem = [float(r["premium"]) for r in rows] or [0.0]
        warn = "" if len(rows) >= expect * 0.9 else f"  WARNING expected ~{expect}"
        print(f"{coin:6s} {len(rows):5d} pts  premium min {min(prem):+.5f} "
              f"max {max(prem):+.5f}{warn}")
        time.sleep(0.2)


def cmd_candles(a):
    """CAUTION: returns the most recent 5000 bars and ignores startTime for
    older windows. There is no backward paging. Reach by interval:
      1m 3.5d | 5m 17d | 15m 52d | 1h 208d | 4h 833d | 1d full
    For anything older than that, use `binance` or the S3 archive."""
    reach = 5000 * IV_MIN.get(a.interval, 1) / 1440
    if a.days > reach:
        print(f"!! {a.interval} reaches only ~{reach:.1f} days back. "
              f"You asked for {a.days}. Use a coarser interval or `binance`.\n")
    end = int(time.time() * 1000)
    for coin in a.coins:
        rows = post({"type": "candleSnapshot",
                     "req": {"coin": coin, "interval": a.interval,
                             "startTime": end - a.days * 86_400_000,
                             "endTime": end}})
        span = (end - rows[0]["t"]) / 86_400_000 if rows else 0
        print(f"{coin:6s} {len(rows):6d} bars  {span:.1f} days back")
        time.sleep(0.2)


# -------------------------------------------------------- Binance public data
def _binance(kind, path, symbol, date):
    url = f"{BINANCE}/{kind}/{symbol}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = z.namelist()[0]
    return z.read(name).decode(), f"{len(blob)/2**20:.2f} MiB"


def cmd_binance(a):
    """Free, no account, no credentials. Reaches back years, unlike the HL API."""
    os.makedirs(a.out, exist_ok=True)
    sym, d = a.symbol, a.date
    jobs = [("klines",  f"1m/{sym}-1m-{d}.zip",       f"{sym}-1m-{d}.csv"),
            ("metrics", f"{sym}-metrics-{d}.zip",     f"{sym}-metrics-{d}.csv")]
    if a.trades:
        jobs.append(("aggTrades", f"{sym}-aggTrades-{d}.zip", f"{sym}-aggTrades-{d}.csv"))
    for kind, path, out in jobs:
        txt, note = _binance(kind, path, sym, d)
        if txt is None:
            print(f"{kind:10s} {note}")
            continue
        dst = os.path.join(a.out, out)
        open(dst, "w").write(txt)
        print(f"{kind:10s} {note:>10s}  {len(txt.splitlines()):>8d} rows  -> {dst}")
    print("\nNOTE: liquidationSnapshot is 404 on Binance. Forced-flow labels "
          "come from the Hyperliquid S3 archive, not from here.")


# ------------------------------------------------------------------------- S3
def cmd_ls(a):
    try:
        import boto3
    except ImportError:
        sys.exit("pip install boto3")
    bucket, base = BUCKETS[a.bucket]
    s3 = boto3.client("s3", region_name=a.region)
    tot, n, sample, tok = 0, 0, [], None
    while True:
        kw = dict(Bucket=bucket, Prefix=base + a.prefix,
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
    print(f"s3://{bucket}/{base + a.prefix}\nobjects {n}   total {gib:.3f} GiB")
    print(f"egress to laptop ~${gib*EGRESS_USD_PER_GIB:.2f}   "
          f"same-region EC2 $0.00 + ~${n*4e-7:.4f} GETs")
    for k, sz in sample:
        print(f"  {sz/2**20:9.2f} MiB  {k}")
    if n == 0:
        print("\nEMPTY. Wrong prefix or wrong region. Re-run with --prefix '' first.")
    if not a.confirm:
        print("\nDry run. Nothing transferred.")
        return
    if tot / 2**20 > a.budget_mib:
        sys.exit(f"REFUSED: {tot/2**20:.1f} MiB over budget {a.budget_mib} MiB.")
    os.makedirs(a.out, exist_ok=True)
    for k, _ in sample:
        s3.download_file(bucket, k, os.path.join(a.out, k.replace("/", "__")),
                         ExtraArgs={"RequestPayer": "requester"})
        print("got", k)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("candles", "funding"):
        q = sub.add_parser(name)
        q.add_argument("--coins", nargs="+", default=["BTC", "ETH", "SOL"])
        q.add_argument("--days", type=int, default=3)
        q.add_argument("--interval", default="1m", choices=list(IV_MIN))
    q = sub.add_parser("binance")
    q.add_argument("--date", required=True, help="YYYY-MM-DD")
    q.add_argument("--symbol", default="BTCUSDT")
    q.add_argument("--trades", action="store_true", help="also pull ~50 MiB aggTrades")
    q.add_argument("--out", default="./raw/binance")
    q = sub.add_parser("ls")
    q.add_argument("--bucket", choices=list(BUCKETS), default="reservoir")
    q.add_argument("--region", default="us-east-1")
    q.add_argument("--prefix", default="")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--confirm", action="store_true")
    q.add_argument("--budget-mib", type=float, default=50.0)
    q.add_argument("--out", default="./raw")
    a = p.parse_args()
    {"candles": cmd_candles, "funding": cmd_funding,
     "binance": cmd_binance, "ls": cmd_ls}[a.cmd](a)


if __name__ == "__main__":
    main()
