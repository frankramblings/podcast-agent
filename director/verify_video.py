#!/usr/bin/env python3
"""Automated lip-sync QA for a rendered master: VIDEO placement per one-shot.

The master is cut on the composite clock, so during a one-shot of host H the
master's video content must equal the composite's H-tile content at the SAME
timestamp. For each one-shot segment in the cutlist we xcorr motion series
(master full-frame vs composite tile) over +/-search seconds; the peak lag is
the video placement error of that segment. 0 within a frame or two = good.

This is the video analog of the old measure_output.py audio check (now only in
git history), which historically read 14ms while lips were >1s off -- audio
verification does NOT cover video placement; this does.

Usage:
  verify_video.py --master <master.mp4> --comp <composite.mp4> \
      --cutlist <dyn_cutlist.json> [--min-seg 8] [--search 3] [--max-segs 12]
"""
import argparse, json, subprocess
import numpy as np
from vidsync_map import xcorr_peak, FPS, DW, DH, TILE
from vidsync import _accept


def motion_win(path, start, dur, boxes=None):
    """Motion series for a window. boxes=None -> full frame (one array);
    boxes={name: (x0,y0,x1,y1)} -> {name: array}, one decode for all."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", path, "-an", "-vf", f"fps={FPS},scale={DW}:{DH},format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    buf = np.frombuffer(r.stdout, np.uint8)
    n = len(buf) // (DW * DH)
    fr = buf[:n * DW * DH].reshape(n, DH, DW).astype(np.int16)
    if n < 2:
        z = np.zeros(0, np.float32)
        return z if boxes is None else {k: z for k in boxes}
    d = np.abs(np.diff(fr, axis=0))
    if boxes is None:
        return d.mean(axis=(1, 2)).astype(np.float32)
    return {k: d[:, y0:y1, x0:x1].mean(axis=(1, 2)).astype(np.float32)
            for k, (x0, y0, x1, y1) in boxes.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--comp", required=True)
    ap.add_argument("--cutlist", required=True)
    ap.add_argument("--min-seg", type=float, default=8.0)
    ap.add_argument("--search", type=float, default=3.0)
    ap.add_argument("--max-segs", type=int, default=12)
    ap.add_argument("--minsharp", type=float, default=1.3)
    ap.add_argument("--offset", type=float, default=None,
                    help="master time = composite time + offset (cold-open "
                         "pre-roll). Default: auto = master_dur - comp_dur "
                         "when the cutlist covers the full episode, else 0.")
    args = ap.parse_args()

    cl = json.load(open(args.cutlist))
    A = cl.get("window", [0.0, 0.0])[0]
    if args.offset is None:
        dur = lambda p: float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", p]).strip())
        args.offset = dur(args.master) - (cl.get("window", [0, 0])[1] - A) if A == 0 else 0.0
        if abs(args.offset) < 0.2:
            args.offset = 0.0
        else:
            print(f"[auto] cold-open offset = {args.offset:+.3f}s "
                  f"(master duration minus composite window)")
    A -= args.offset
    segs = [s for s in cl["segs"] if s["stream"] in ("tim", "frank")
            and s["end"] - s["start"] >= args.min_seg]
    # spread the checked segments across the episode
    if len(segs) > args.max_segs:
        idx = np.linspace(0, len(segs) - 1, args.max_segs).astype(int)
        segs = [segs[i] for i in idx]
    if not segs:
        print("no one-shot segments long enough to verify"); return

    M = args.search
    TRIM = 0.4    # keep the master signal clear of its own cut transitions
    wins = lambda x: np.minimum(x, np.percentile(x, 95)) if len(x) else x
    print(f"{'host':>6} {'comp t':>9} {'len':>5} | {'lag(s)':>7} {'sharp':>6} {'region':>6} | verdict")
    worst, results = 0.0, []
    for s in segs:
        t0, t1 = s["start"], s["end"]
        # SEGMENT-ONLY master signal slid over an EXTENDED composite reference.
        # (The old way -- extended master vs exact composite -- pulled the
        # neighboring shots' hard cuts into the signal; cut spikes lining up
        # with composite layout-switch spikes made razor-sharp bogus locks.)
        seg_sig = wins(motion_win(args.master, (t0 - A) + TRIM, (t1 - t0) - 2 * TRIM))
        refs = motion_win(args.comp, t0 + TRIM - M, (t1 - t0) - 2 * TRIM + 2 * M, TILE)
        n = len(seg_sig)
        if n < FPS * 4 or max(len(r) for r in refs.values()) < n + FPS:
            print(f"{s['stream']:>6} {t0:9.1f} {t1-t0:5.1f} | window unavailable")
            continue
        best = None
        for name, ref in refs.items():
            d, sh, sc = xcorr_peak(wins(ref), seg_sig)
            if d is not None and sh >= args.minsharp and (best is None or sh > best[1]):
                best = (d, sh, sc, name)
        if best is None:
            print(f"{s['stream']:>6} {t0:9.1f} {t1-t0:5.1f} | {'--':>7} {'':>6} {'':>6} | no confident peak")
            continue
        d, sh, sc, name = best
        # match position in comp = t0+TRIM-M+d/FPS; master@x shows comp@(x-lag)
        lag = -(d / FPS - M)
        # tiered trust: an OFF verdict is an accusation -- it needs BOTH the
        # per-cut acceptance rule AND a strong content match (score >= 0.5).
        # Low-score locks near-but-not-at zero are phantom (570@508: +0.469 at
        # score 0.37 while the master sat exactly on the map per an own-camera
        # lock at score 0.89). OK verdicts at ~0 need no gate: they agree.
        if abs(lag) > 2.5 / FPS and (sc < 0.5 or not _accept(lag, sh, sc)):
            print(f"{s['stream']:>6} {t0:9.1f} {t1-t0:5.1f} | {lag:+7.3f} {sh:6.2f} {name:>6} | weak lock (not judged)")
            continue
        results.append(lag); worst = max(worst, abs(lag))
        verdict = "OK" if abs(lag) <= 2.5 / FPS else "OFF"
        print(f"{s['stream']:>6} {t0:9.1f} {t1-t0:5.1f} | {lag:+7.3f} {sh:6.2f} {name:>6} | {verdict}")
    if results:
        print(f"\nchecked {len(results)} one-shots: median {np.median(results):+.3f}s"
              f"  worst {worst:.3f}s  ({'PASS' if worst <= 0.12 else 'FAIL'},"
              f" tolerance 0.12s ~= EBU R37 territory)")


if __name__ == "__main__":
    main()
