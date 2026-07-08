#!/usr/bin/env python3
"""
Competitive gating detector — the real-footage fix for mic bleed.

The synthetic spike used absolute silencedetect per stem. On real footage Tim's
mic hears Frank (and vice-versa), so absolute thresholds light up BOTH mics and
the Director collapses to composite forever.

Competitive gating instead asks, per analysis frame: who is LOUDER, and by how
much?  loudest-by-a-margin wins a solo; genuinely-close-and-both-loud = overlap
(2-shot); both-quiet = nobody (safe wide). This is robust to bleed because bleed
is, by construction, quieter than the person actually talking into the mic.

stdlib + ffmpeg only. No numpy.

Usage:
    python3 gate.py frank.wav tim.wav [--start S] [--dur D]
                    [--hop 0.05] [--floor -45] [--margin 6]
"""
import subprocess, sys, array, math, json, argparse

def decode_pcm(path, sr, start, dur):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None: cmd += ["-ss", str(start)]
    if dur is not None:   cmd += ["-t", str(dur)]
    cmd += ["-i", path, "-ac", "1", "-ar", str(sr),
            "-af", "highpass=f=85",          # kill room rumble / HVAC
            "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    a = array.array("h"); a.frombytes(r.stdout)
    return a

def rms_db_track(a, sr, hop):
    """Non-overlapping RMS windows -> dBFS list."""
    n = max(1, int(sr * hop))
    out = []
    total = len(a)
    i = 0
    while i + n <= total:
        s = 0
        # local sum of squares
        seg = a[i:i+n]
        for v in seg:
            s += v * v
        rms = math.sqrt(s / n)
        out.append(20.0 * math.log10(rms / 32768.0 + 1e-9))
        i += n
    return out

def decide(fr, tm, floor, margin):
    """Per-frame state from two dB tracks."""
    states = []
    for a, b in zip(fr, tm):
        a_on = a > floor
        b_on = b > floor
        if not a_on and not b_on:
            states.append("nobody")
        elif a_on and not b_on:
            states.append("frank")
        elif b_on and not a_on:
            states.append("tim")
        else:  # both above floor -> who dominates?
            if a - b >= margin:
                states.append("frank")
            elif b - a >= margin:
                states.append("tim")
            else:
                states.append("both")
    return states

def smooth(states, k):
    """Majority-vote smoothing over a window of k frames to kill 1-frame flips."""
    if k <= 1: return states
    out = []
    h = k // 2
    for i in range(len(states)):
        lo, hi = max(0, i-h), min(len(states), i+h+1)
        win = states[lo:hi]
        out.append(max(set(win), key=win.count))
    return out

def segments(states, hop):
    segs = []
    for i, s in enumerate(states):
        t = i * hop
        if segs and segs[-1]["who"] == s:
            segs[-1]["end"] = t + hop
        else:
            segs.append({"who": s, "start": t, "end": t + hop})
    return segs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frank"); ap.add_argument("tim")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--sr", type=int, default=8000)
    ap.add_argument("--hop", type=float, default=0.05)
    ap.add_argument("--floor", type=float, default=-45.0)
    ap.add_argument("--margin", type=float, default=6.0)
    ap.add_argument("--smooth", type=int, default=5)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    fr = rms_db_track(decode_pcm(a.frank, a.sr, a.start, a.dur), a.sr, a.hop)
    tm = rms_db_track(decode_pcm(a.tim,   a.sr, a.start, a.dur), a.sr, a.hop)
    n = min(len(fr), len(tm)); fr, tm = fr[:n], tm[:n]

    # quick level stats so we can see the bleed gap
    def pct(xs, p): xs=sorted(xs); return xs[int(p*(len(xs)-1))]
    print(f"frames={n} hop={a.hop}s  span={n*a.hop:.1f}s")
    print(f"frank dB  p10={pct(fr,.1):6.1f} p50={pct(fr,.5):6.1f} p90={pct(fr,.9):6.1f}")
    print(f"tim   dB  p10={pct(tm,.1):6.1f} p50={pct(tm,.5):6.1f} p90={pct(tm,.9):6.1f}")

    states = smooth(decide(fr, tm, a.floor, a.margin), a.smooth)
    counts = {k: states.count(k) for k in ("frank","tim","both","nobody")}
    tot = len(states)
    print("\nstate distribution:")
    for k in ("frank","tim","both","nobody"):
        print(f"  {k:<7} {counts[k]*a.hop:6.1f}s  {100*counts[k]/tot:4.1f}%")

    segs = [s for s in segments(states, a.hop)]
    # report only shots >= 0.4s so the timeline is readable
    big = [s for s in segs if s["end"]-s["start"] >= 0.4]
    print(f"\nraw shots={len(segs)}  (>=0.4s shown: {len(big)})")
    print(f"{'who':<7}{'start':>8}{'end':>8}{'len':>7}")
    for s in big[:60]:
        print(f"{s['who']:<7}{s['start']:>8.2f}{s['end']:>8.2f}{s['end']-s['start']:>7.2f}")

    if a.json:
        json.dump({"hop":a.hop,"floor":a.floor,"margin":a.margin,
                   "states":states,"segments":segs}, open(a.json,"w"))
        print(f"\nwrote {a.json}")

if __name__ == "__main__":
    main()
