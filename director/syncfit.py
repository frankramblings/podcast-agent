#!/usr/bin/env python3
"""Splice-aware robust offset fit.

The composite audio bed (our reference clock) was recorded/stitched with one or
more ~2-3s discontinuities: relative to composite, EVERY camera shows the same
sudden backward jump in offset at the same timestamp, on top of a slow +drift
from clock skew. A single least-squares line (what Tim used) tilts through the
sawtooth and drifts; a single constant (what Frank used) sits in the middle and
is wrong at both ends. Both fail for the same reason.

This module measures a dense offset series per camera, rejects bad GCC-PHAT
locks, detects the splice point(s), and fits a robust (Theil-Sen) line PER
segment. off(t) evaluates the right segment and extrapolates the first/last
segment past the probe range (so the cold open at t<first-probe is covered).
"""
import numpy as np


def probe_series(measure, path, total, step=60, edge=48, minsharp=50):
    """[(t, lag)] of confident same-clock GCC-PHAT probes across the episode."""
    pts = []
    for t in range(edge, int(total) - edge, step):
        lag, sh = measure(path, t, t)
        if lag is not None and sh > minsharp:
            pts.append((float(t), float(lag)))
    return pts


def _theil_sen(xs, ys):
    """Median-of-pairwise-slopes line; robust to outliers. Returns (slope, intr)."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    if len(xs) == 1:
        return 0.0, float(ys[0])
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i])
              for i in range(len(xs)) for j in range(i + 1, len(xs))
              if xs[j] != xs[i]]
    s = float(np.median(slopes)) if slopes else 0.0
    b = float(np.median(ys - s * xs))
    return s, b


def _reject_outliers(pts, win=3, tol=1.2):
    """Drop points whose lag deviates > tol from the median of their local window
    (after removing the global robust trend, so the sawtooth ramp isn't cut)."""
    if len(pts) < 5:
        return pts
    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    g, gi = _theil_sen(xs, ys)
    r = ys - (g * xs + gi)                       # detrended residual
    keep = []
    for i in range(len(pts)):
        lo = max(0, i - win); hi = min(len(pts), i + win + 1)
        local = np.median(np.delete(r[lo:hi], min(i - lo, len(r[lo:hi]) - 1)))
        if abs(r[i] - local) <= tol:
            keep.append(pts[i])
    return keep if len(keep) >= 2 else pts


def detect_splices(pts, jump=1.0, both_dirs=False):
    """Times where the offset jumps backward > `jump` between adjacent confident
    points (a composite-bed splice) rather than drifting slowly forward.
    both_dirs=True also splits on FORWARD jumps -- video timelines (vidsync) can
    step either way at an upload seam, and interpolating across a step ramps the
    offset through values that were never real."""
    sp = []
    for i in range(1, len(pts)):
        d = pts[i][1] - pts[i - 1][1]
        if d < -jump or (both_dirs and d > jump):
            sp.append((pts[i - 1][0] + pts[i][0]) / 2.0)
    return sp


class PiecewiseOffset:
    """Callable off(t): robust linear within each inter-splice segment,
    first/last segment extrapolated to cover episode edges (incl. cold open)."""
    def __init__(self, bounds, lines):
        self.bounds = bounds      # [(seg_start, seg_end), ...] on composite clock
        self.lines = lines        # [(slope, intercept), ...]

    def __call__(self, t):
        for (a, b), (s, i) in zip(self.bounds, self.lines):
            if a <= t < b:
                return s * t + i
        # extrapolate: before first -> first line; after last -> last line
        if t < self.bounds[0][0]:
            s, i = self.lines[0]
        else:
            s, i = self.lines[-1]
        return s * t + i


def _seg_slope(xs, ys, at_start):
    """Robust local slope at a segment edge, for extrapolating past the probes.
    Uses the Theil-Sen slope of the segment (median pairwise) so a single noisy
    edge point can't tilt the cold-open/tail extrapolation."""
    if len(xs) < 2:
        return 0.0
    s, _ = _theil_sen(xs, ys)
    return s


class InterpOffset:
    """Callable off(t): piecewise-LINEAR INTERPOLATION through the measured probe
    points within each inter-splice segment, with robust linear extrapolation
    beyond the first/last probe of a segment (covers the cold open and tail).

    Why interpolation, not a fitted line: within a segment the true offset drifts
    with a slight curve (variable clock skew), so a single straight line leaves a
    ~0.5s worst-case error right at the cold open. Connecting the measured points
    directly hugs that curve; residual is bounded by between-probe curvature, which
    dense probing (30s) drives well under lip-sync tolerance. Splices still break
    the domain into segments so we never interpolate ACROSS a discontinuity."""
    def __init__(self, seg_bounds, seg_pts):
        self.bounds = seg_bounds          # [(a, b), ...]
        self.segs = []                    # [(xs, ys, s0, sN), ...]
        for pts in seg_pts:
            pts = sorted(pts)
            xs = np.array([p[0] for p in pts], float)
            ys = np.array([p[1] for p in pts], float)
            s0 = _seg_slope(xs, ys, True)   # slope for pre-first extrapolation
            sN = s0                          # same robust slope for tail
            self.segs.append((xs, ys, s0, sN))

    def _eval_seg(self, xs, ys, s0, sN, t):
        if len(xs) == 1:
            return float(ys[0])
        if t <= xs[0]:
            return float(ys[0] + s0 * (t - xs[0]))    # extrapolate before first probe
        if t >= xs[-1]:
            return float(ys[-1] + sN * (t - xs[-1]))  # extrapolate after last probe
        return float(np.interp(t, xs, ys))            # interpolate between probes

    def __call__(self, t):
        for (a, b), (xs, ys, s0, sN) in zip(self.bounds, self.segs):
            if a <= t < b and len(xs):
                return self._eval_seg(xs, ys, s0, sN, t)
        # outside all bounds -> nearest segment, extrapolated
        if t < self.bounds[0][0]:
            xs, ys, s0, sN = self.segs[0]
        else:
            xs, ys, s0, sN = self.segs[-1]
        if not len(xs):
            return 1.8
        return self._eval_seg(xs, ys, s0, sN, t)


def _loo_maxresid(seg_pts):
    """Honest error estimate: for each interior probe, drop it and predict it from
    its neighbors via the same linear interpolation. Max over all segments. This is
    what the between-probe error actually is at render time (the model never sees
    the exact point it's evaluating between cuts)."""
    worst = 0.0
    for pts in seg_pts:
        pts = sorted(pts)
        if len(pts) < 3:
            continue
        for i in range(1, len(pts) - 1):
            rest = pts[:i] + pts[i + 1:]
            xs = np.array([p[0] for p in rest], float)
            ys = np.array([p[1] for p in rest], float)
            pred = float(np.interp(pts[i][0], xs, ys))
            worst = max(worst, abs(pred - pts[i][1]))
    return worst


def fit_from_points(pts, lo, hi, jump=1.0, verbose=False, label="", both_dirs=False):
    """Piecewise INTERPOLATING fit from ALREADY-MEASURED (composite_t, lag) points
    over the domain [lo, hi]. Splits at detected splices, then interpolates through
    the measured points within each segment (robust linear extrapolation past the
    edge probes for the cold open / tail). This is the shared core; callers supply
    the points so the probe geometry (continuous feed vs chunk-local) lives with
    them. Falls back to a constant when too few points."""
    pts = _reject_outliers(pts)
    if len(pts) < 2:
        m = float(np.median([p[1] for p in pts])) if pts else 1.8
        po = InterpOffset([(lo, hi)], [[(lo, m)]])
        if verbose: print(f"    fit {label}: <2 pts, const {m:+.3f}")
        return po, {"n": len(pts), "splices": [], "segs": [(lo, hi, 0.0, m)]}

    splices = detect_splices(pts, jump=jump, both_dirs=both_dirs)
    edges = [float(lo)] + splices + [float(hi)]
    bounds, seg_pts, segrep = [], [], []
    allx = [p[0] for p in pts]; ally = [p[1] for p in pts]
    for k in range(len(edges) - 1):
        a, b = edges[k], edges[k + 1]
        seg = [p for p in pts if a <= p[0] < b]
        if len(seg) == 0:
            # no probes in this segment: borrow the global robust line as 2 anchors
            gs, gi = _theil_sen(allx, ally)
            seg = [(a, gs * a + gi), (b, gs * b + gi)]
        bounds.append((a, b)); seg_pts.append(seg)
        s, _ = _theil_sen([p[0] for p in seg], [p[1] for p in seg]) if len(seg) > 1 else (0.0, 0.0)
        segrep.append((a, b, s, seg[0][1]))
    po = InterpOffset(bounds, seg_pts)

    # honest residuals: single-line LS (what shipped, the thing we're replacing)
    # vs leave-one-out interpolation (what this model actually does between probes)
    xs = np.array(allx); ys = np.array(ally)
    la, lb = np.polyfit(xs, ys, 1)
    ls_res = float(np.max(np.abs(ys - (la * xs + lb))))
    loo_res = _loo_maxresid(seg_pts)
    info = {"n": len(pts), "splices": splices, "segs": segrep,
            "ls_maxresid": ls_res, "pw_maxresid": loo_res, "loo_maxresid": loo_res}
    if verbose:
        print(f"    fit {label}: n={len(pts)} splices={[round(s) for s in splices]} "
              f"LS_maxresid={ls_res:.3f}s -> interp_LOO={loo_res:.3f}s")
    return po, info


def fit(measure, path, total, step=60, minsharp=50, jump=1.0, verbose=False):
    """Build a PiecewiseOffset for a CONTINUOUS feed (local time == composite
    time), e.g. Tim's single camera. Probes then delegates to fit_from_points."""
    raw = probe_series(measure, path, total, step=step, minsharp=minsharp)
    return fit_from_points(raw, 0.0, float(total), jump=jump, verbose=verbose,
                           label=path.split('/')[-1][:30])
