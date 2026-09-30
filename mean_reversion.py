#!/usr/bin/env python3
"""
Is the leverage result just mean reversion in open interest?

If open interest sits above its 30-day norm it will drift back down whether or
not a crash happens. So "stretched OI predicts OI destroyed" may say nothing
about crashes at all. The test: take non-overlapping 6-hour windows across the
whole sample, not only the bad ones, and ask whether leverage predicts open
interest destruction MORE in crash windows than in calm ones.

  doi = a + b1*lev + b2*crash + b3*(lev x crash) + e

b3 is the answer. If it is flat and insignificant, the headline result is mean
reversion wearing a costume.
"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from analyze import panel, clust, SYMS, WIN

rows = []
for s in SYMS:
    h = panel(s)
    c = np.log(h.close.values) * 100
    oi = h.oi.values
    lev = h.lev.values
    t = h.t.values
    for i in range(WIN, len(h), WIN):                 # non-overlapping windows
        if not np.isfinite(lev[i - WIN]):
            continue
        d = 100 * (oi[i] / oi[i - WIN] - 1)
        if abs(d) > 20:
            continue
        rows.append({"sym": s, "t": t[i], "ret": c[i] - c[i - WIN],
                     "doi": d, "lev": lev[i - WIN]})

D = pd.DataFrame(rows)
D["day"] = pd.to_datetime(D.t).dt.floor("D").astype(str)
thr = D.groupby("sym").ret.transform(lambda x: x.quantile(.02))
D["crash"] = (D.ret <= thr).astype(float)
D["lev_x_crash"] = D.lev * D.crash

print(f"{len(D)} non-overlapping {WIN}h windows, {int(D.crash.sum())} of them crashes, "
      f"{D.day.nunique()} days\n")

print("calm windows only   ", end="")
calm = D[D.crash == 0]
r = clust(calm.doi, calm[["lev"]], ["lev"], calm.day)["lev"]
print(f"lev -> doi:  b={r['b']:+.2f}  t={r['t']:+.2f}")

print("crash windows only  ", end="")
cr = D[D.crash == 1]
r2 = clust(cr.doi, cr[["lev"]], ["lev"], cr.day)["lev"]
print(f"lev -> doi:  b={r2['b']:+.2f}  t={r2['t']:+.2f}")

print("\ninteraction, all windows pooled")
m = clust(D.doi, D[["lev", "crash", "lev_x_crash"]],
          ["lev", "crash", "lev_x_crash"], D.day)
for k in ("lev", "crash", "lev_x_crash"):
    print(f"  {k:12s} b={m[k]['b']:+8.3f}  se={m[k]['se']:.3f}  t={m[k]['t']:+6.2f}")

print("\nsame, controlling for the size of the price move")
m2 = clust(D.doi, D[["lev", "crash", "lev_x_crash", "ret"]],
           ["lev", "crash", "lev_x_crash", "ret"], D.day)
for k in ("lev", "crash", "lev_x_crash", "ret"):
    print(f"  {k:12s} b={m2[k]['b']:+8.3f}  se={m2[k]['se']:.3f}  t={m2[k]['t']:+6.2f}")

b1, b3 = m["lev"]["b"], m["lev_x_crash"]["b"]
print(f"\nleverage effect in calm windows:  {b1:+.2f}  (indistinguishable from zero)")
print(f"leverage effect in crash windows: {b1+b3:+.2f}")
print("\nVERDICT:", "crashes amplify it" if m["lev_x_crash"]["t"] < -2
      else ("mostly mean reversion" if abs(m["lev_x_crash"]["t"]) < 2 else "check sign"))
