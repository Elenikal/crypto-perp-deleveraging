#!/usr/bin/env python3
"""Pull free Binance USD-M futures data. No account, no credentials, no cost."""
import io, os, sys, zipfile, datetime as dt, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE = "https://data.binance.vision/data/futures/um"
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
START, END = dt.date(2024, 10, 1), dt.date(2026, 9, 25)

def grab(url, dst):
    if os.path.exists(dst):
        return "cached"
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:
        return type(e).__name__
    z = zipfile.ZipFile(io.BytesIO(blob))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(z.read(z.namelist()[0]))
    return "ok"

def jobs():
    j = []
    for s in SYMS:
        m = dt.date(START.year, START.month, 1)
        while m <= END:
            tag = f"{m.year}-{m.month:02d}"
            j.append((f"{BASE}/monthly/klines/{s}/5m/{s}-5m-{tag}.zip",
                      f"{OUT}/klines/{s}/{tag}.csv"))
            m = dt.date(m.year + m.month // 12, m.month % 12 + 1, 1)
        d = START
        while d <= END:
            j.append((f"{BASE}/daily/metrics/{s}/{s}-metrics-{d}.zip",
                      f"{OUT}/metrics/{s}/{d}.csv"))
            d += dt.timedelta(days=1)
    return j

if __name__ == "__main__":
    js = jobs()
    print(f"{len(js)} files across {len(SYMS)} symbols", flush=True)
    done = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i, r in enumerate(ex.map(lambda a: grab(*a), js), 1):
            done[r] = done.get(r, 0) + 1
            if i % 250 == 0:
                print(f"  {i}/{len(js)}  {done}", flush=True)
    print("FINAL", done, flush=True)
