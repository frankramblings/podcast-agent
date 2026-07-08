#!/usr/bin/env python3
"""Diagnostic: measure true per-cam GCC-PHAT offset vs composite across an
episode, compare Tim's linear fit and Frank's constant against the raw probes.

Usage: python3 probe_offsets.py --feeds /path/to/feeds/<id>
"""
import argparse, numpy as np
import render_full as rf
from render_ep import discover

ap = argparse.ArgumentParser()
ap.add_argument("--feeds", required=True)
args = ap.parse_args()

comp, tim, frank = discover(args.feeds)
rf.COMP = comp; rf.TIM = tim
rf.CHUNKS = [{"start":0.0,"end":rf.dur(comp),"path":frank,"off":None}]
total = rf.dur(comp)
print(f"total={total:.1f}s\nCOMP={comp}\nTIM={tim}\nFRANK={frank}\n")

ts = [t for t in range(20, int(total)-20, 120)]
print(f"{'t':>6} | {'TIM lag':>9} {'sh':>6} | {'FRANK lag':>9} {'sh':>6}")
tim_pts, frank_pts = [], []
for t in ts:
    tl, tsh = rf.measure(rf.TIM, t, t)
    fl, fsh = rf.measure(frank, t, t)
    if tl is not None and tsh > 50: tim_pts.append((t, tl))
    if fl is not None and fsh > 50: frank_pts.append((t, fl))
    tls = f"{tl:+.3f}" if tl is not None else "  none "
    fls = f"{fl:+.3f}" if fl is not None else "  none "
    print(f"{t:>6} | {tls:>9} {tsh:>6.0f} | {fls:>9} {fsh:>6.0f}")

def report(name, pts):
    if len(pts) < 2:
        print(f"\n{name}: <2 confident points, cannot fit"); return
    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    a, b = np.polyfit(xs, ys, 1)                    # least-squares (what code uses)
    resid = ys - (a*xs + b)
    # robust: median slope of all pairs (Theil-Sen-ish) + median intercept
    slopes = [(ys[j]-ys[i])/(xs[j]-xs[i]) for i in range(len(xs)) for j in range(i+1,len(xs))]
    rs = float(np.median(slopes)); ri = float(np.median(ys - rs*xs))
    print(f"\n{name}: n={len(pts)}")
    print(f"  LS  fit: off(t)={a:+.6f}*t {b:+.3f}   max|resid|={np.max(np.abs(resid)):.3f}s  std={np.std(resid):.3f}s")
    print(f"  ROB fit: off(t)={rs:+.6f}*t {ri:+.3f}   (median-slope / median-intercept)")
    print(f"  const median={np.median(ys):+.3f}s  spread(min..max)={ys.min():+.3f}..{ys.max():+.3f}")
    # drift across episode implied by robust slope:
    print(f"  robust drift end-to-end = {rs*total*1000:+.0f} ms over {total:.0f}s")

report("TIM", tim_pts)
report("FRANK", frank_pts)
