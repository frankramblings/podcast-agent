#!/usr/bin/env python3
"""Build a VIDEO offset map voff(t) for a camera against the composite VIDEO.

Why this exists: the Wistia 'camera backup' files stamp video as gapless CFR
even though the capture dropped frames, so the video PTS axis drifts vs the
file's own (sample-accurate) audio by a time-VARYING amount. Audio-derived
offsets therefore cannot place video. The composite video is ground truth
(its lips are verified in sync) and contains each host's tile, so we align
camera video to composite video directly via motion-energy cross-correlation
-- same-modality, same-content, sharp peaks.

Method:
  1. Stream-decode composite + camera once at 192x108 gray 30fps; reduce each
     frame to a region motion value (mean |frame diff| over the host's tile /
     the camera's matching region) -> two 1-D series, whole episode.
  2. Audio offset points aoff(t) every audio_step via GCC-PHAT (existing pcm
     machinery) -- these center the video search windows.
  3. Every step seconds: z-normalized cross-correlation of the composite tile
     window [t-W/2, t+W/2) against the camera series around t+aoff(t), lag
     range +/-margin. Confident peaks (peak/runner >= minsharp) become video
     offset points voff(t) = camera_video_seek_for_composite_t - t.
  4. syncfit.fit_from_points -> splice-aware piecewise voff(t); JSON out.

Usage:
  vidsync_map.py --cam <camera.mp4> --comp <composite.mp4> --host tim \
      [--out vmap_tim.json] [--step 30 --w 45 --margin 6]
Tiles (566-style layout, 1920x1080 composite): tim=left, frank=right.
"""
import subprocess, argparse, json, sys
import numpy as np
from chunks import pcm, gcc_phat, SR
import syncfit

FPS = 30
DW, DH = 192, 108          # decode grid (1920x1080 / 10)
# candidate regions on the decode grid: (x0, y0, x1, y1). The composite layout
# is DYNAMIC (active-speaker reordering): a host may sit in either tile or be
# full-screen at any moment, so alignment always tries every region and keeps
# the best lock. Names are positional, not host-bound.
TILE = {"left":  (5, 5, 93, 103),    # crop 886x986+49+47  /10
        "right": (98, 5, 187, 103),  # crop 886x986+985+47 /10
        "full":  (0, 0, DW, DH)}
CAMBOX = (33, 0, 131, 108)          # crop ~970x1080+335+0 /10


def motion_series(path, boxes, label):
    """Decode once; return {name: per-frame mean |diff| over box} at FPS.
    `boxes` may be a single (x0,y0,x1,y1) tuple (returns one array) or a
    {name: box} dict (returns {name: array}) -- all reduced in ONE decode."""
    single = not isinstance(boxes, dict)
    bd = {"_": boxes} if single else boxes
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", path, "-an",
         "-vf", f"fps={FPS},scale={DW}:{DH},format=gray",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    fsz = DW * DH
    prev, n = None, 0
    out = {k: [] for k in bd}
    while True:
        buf = p.stdout.read(fsz)
        if len(buf) < fsz:
            break
        a = np.frombuffer(buf, np.uint8).reshape(DH, DW).astype(np.int16)
        if prev is not None:
            d = np.abs(a - prev)
            for k, (x0, y0, x1, y1) in bd.items():
                out[k].append(float(d[y0:y1, x0:x1].mean()))
        prev = a
        n += 1
        if n % 18000 == 0:
            print(f"    [{label}] {n/FPS/60:.0f}min decoded", flush=True)
    p.wait()
    print(f"    [{label}] done: {n} frames ({n/FPS:.1f}s)", flush=True)
    res = {k: np.asarray(v, np.float32) for k, v in out.items()}
    return res["_"] if single else res


def zn(x):
    return (x - x.mean()) / (x.std() + 1e-9)


def xcorr_peak(sig, ref, min_score=0.15):
    """Slide ref over sig; return (best_lag_frames_subframe, sharpness, score).
    `score` is the peak's absolute zncc -- the content-match strength. Sharpness
    (peak/runner-up) measures uniqueness but NOT truth: sustained-low-motion
    windows produce sharp yet WRONG locks (score ~0.2-0.3) while true
    same-content locks score ~0.5+. Gate large decisions on score.
    Windows with ~no motion or peak < min_score return sharpness 0."""
    n = len(ref)
    lags = len(sig) - n
    if lags < 3 or ref.std() < 1e-3 or sig.std() < 1e-3:
        return None, 0.0, 0.0
    ref_z = zn(ref)
    score = np.empty(lags)
    for d in range(lags):
        score[d] = float(np.dot(zn(sig[d:d + n]), ref_z)) / n
    best = int(np.argmax(score))
    if score[best] < min_score:
        return None, 0.0, 0.0
    mask = np.ones(lags, bool)
    mask[max(0, best - FPS // 4):best + FPS // 4 + 1] = False
    runner = float(score[mask].max()) if mask.any() else 0.0
    sharp = score[best] / (abs(runner) + 1e-9)
    # parabolic sub-frame refinement
    b = float(best)
    if 0 < best < lags - 1:
        y0, y1, y2 = score[best - 1], score[best], score[best + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            b += 0.5 * (y0 - y2) / den
    return b, sharp, float(score[best])


def audio_points(cam, comp, total, step, span=90.0, minsharp=45):
    pts = []
    t = span / 2 + 5
    while t < total - span / 2 - 5:
        fr = pcm(cam, t, span); cp = pcm(comp, t, span)
        n = min(len(fr), len(cp))
        if n >= SR * 5:
            lag, sh = gcc_phat(fr[:n], cp[:n], 12)
            if sh > minsharp:
                pts.append((float(t), float(lag)))
        t += step
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", required=True)
    ap.add_argument("--comp", required=True)
    ap.add_argument("--host", default="cam", help="label for the output file only")
    ap.add_argument("--out", default=None)
    ap.add_argument("--step", type=float, default=30.0)
    ap.add_argument("--w", type=float, default=45.0)
    ap.add_argument("--margin", type=float, default=6.0)
    ap.add_argument("--minsharp", type=float, default=1.4)
    ap.add_argument("--audio-step", type=float, default=120.0)
    args = ap.parse_args()

    print(f"[1/3] audio offset points ({args.audio_step:.0f}s grid)...", flush=True)
    total = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.comp]).strip())
    apts = audio_points(args.cam, args.comp, total, args.audio_step)
    if len(apts) < 2:
        print("FATAL: not enough confident audio probes"); sys.exit(1)
    ax = np.array([p[0] for p in apts]); ay = np.array([p[1] for p in apts])
    aoff = lambda t: float(np.interp(t, ax, ay))
    print(f"    {len(apts)} audio points, aoff range "
          f"[{ay.min():+.3f}, {ay.max():+.3f}]", flush=True)

    print("[2/3] decoding motion series (one pass per file)...", flush=True)
    comp_regions = motion_series(args.comp, TILE, "comp")
    cam_m = motion_series(args.cam, CAMBOX, "cam")

    print("[3/3] video offset map (best lock across composite regions)...", flush=True)
    W, M = args.w, args.margin
    nref = int(W * FPS)
    vpts, weak = [], 0
    t = W / 2
    while t < total - W / 2:
        a = aoff(t)
        r0 = int(round((t - W / 2) * FPS))
        c0 = (t - W / 2) + a - M
        s0 = int(round(c0 * FPS))
        sig = cam_m[s0:s0 + nref + int(2 * M * FPS)]
        if s0 < 0 or len(sig) < nref + FPS:
            t += args.step; continue
        best = None
        for name, series in comp_regions.items():
            ref = series[r0:r0 + nref]
            if len(ref) < nref:
                continue
            d, sharp, sc = xcorr_peak(sig, ref)
            if d is not None and sharp >= args.minsharp and (best is None or sharp > best[1]):
                best = (d, sharp, name)
        if best is not None:
            d, sharp, name = best
            voff = a + (d / FPS - M)
            vpts.append((float(t), float(voff)))
            print(f"    t={t:7.1f}  aoff={a:+.3f}  voff={voff:+.3f}  "
                  f"v-a={voff - a:+.3f}  sharp={sharp:.2f}  [{name}]", flush=True)
        else:
            weak += 1
        t += args.step

    print(f"\n{len(vpts)} confident video points ({weak} weak rejected)", flush=True)
    po, info = syncfit.fit_from_points(vpts, 0.0, total, verbose=True,
                                       label=f"video:{args.host}")
    resid = [(t, v - aoff(t)) for (t, v) in vpts]
    if resid:
        rv = [r for _, r in resid]
        print(f"video-audio drift: median {np.median(rv):+.3f}s  "
              f"range [{min(rv):+.3f}, {max(rv):+.3f}]  -- if this is not ~0, "
              f"audio-based video placement is wrong by that much", flush=True)
    out = args.out or f"vmap_{args.host}.json"
    json.dump({"cam": args.cam, "comp": args.comp, "host": args.host,
               "total": total, "w": W, "margin": M, "step": args.step,
               "audio_points": apts, "video_points": vpts,
               "drift": resid, "splices": info["splices"],
               "loo_maxresid": info.get("loo_maxresid")},
              open(out, "w"), indent=1)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
