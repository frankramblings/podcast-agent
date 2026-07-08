#!/usr/bin/env python3
"""Video offset maps for the Director render (importable API over vidsync_map).

The camera-backup files stamp video as gapless CFR even when capture dropped
frames, so a camera's video PTS axis drifts vs its own audio by a time-varying
amount (measured >2s on 566). Audio offsets therefore MUST NOT place video.
This module builds voff(t) per host by aligning camera video to the composite
video (motion-energy xcorr, splice-aware syncfit), with a JSON cache per feeds
dir so a re-render doesn't pay the decode twice.

  maps = vidsync.build_maps(comp, {"tim": tim_path, "frank": frank_path}, feeds_dir)
  maps["tim"]  -> (voff_fn, info)   # voff_fn(t): camera video seek = t + voff(t)

Tile sides are auto-assigned: each camera is trial-correlated against both
composite tiles on a few windows and keeps the side that actually matches.
"""
import os, json
import numpy as np
import syncfit
from vidsync_map import (motion_series, xcorr_peak, audio_points,
                         TILE, CAMBOX, FPS)

SERIES_FILE = "vmotion.npz"


def load_series(cache_dir):
    """{'comp_left':..,'comp_right':..,'comp_full':..,'cam_<host>':..} or None."""
    p = os.path.join(cache_dir, SERIES_FILE)
    if not os.path.exists(p):
        return None
    z = np.load(p)
    return {k: z[k] for k in z.files}


def _accept(rel, sharp, score):
    """Tiered acceptance for a per-cut lock, `rel` = correction vs the map
    prediction. Small corrections need modest confidence. Large corrections
    (camera freeze/catch-up wobbles, up to ~1.4s real) must ALSO have a strong
    absolute content match: sharpness alone lets sustained-low-motion windows
    through (570@340: sharp 4.23 but score 0.31, WRONG by 2s; the true 566
    opener lock scored 0.75). Score >= 0.5 is the discriminator."""
    a = abs(rel)
    return (a <= 0.6 and sharp >= 1.4) or (a <= 3.0 and sharp >= 1.75 and score >= 0.5)


def percut_align(segs, series, preds, margin=3.0, min_len=5.0, verbose=True):
    """Annotate one-shot segs with seg['vseek']: per-SEGMENT video alignment.
    The global map is measured on 45s windows, which average through short
    freeze/catch-up wobbles in a camera's timeline; an individual cut inside a
    wobble is visibly off. Here each seg's own span is aligned against the
    composite regions (numpy only -- series are precomputed), with the map
    prediction as prior/fallback.
      series: from load_series();  preds: {stream: pred_fn(t)->camera seek}."""
    regions = {k.split("_", 1)[1]: series[k] for k in series if k.startswith("comp_")}
    n_ok = n_try = 0
    for s in segs:
        st = s["stream"]
        if st not in preds or preds[st] is None:
            continue
        a, b = s["start"], s["end"]
        if b - a < min_len:
            continue
        cam = series.get(f"cam_{st}")
        if cam is None:
            continue
        pred = preds[st](a)
        nref = int(round((b - a) * FPS))
        r0 = int(round(a * FPS))
        s0 = int(round((pred - margin) * FPS))
        sig = cam[s0:s0 + nref + int(2 * margin * FPS)]
        if s0 < 0 or len(sig) < nref + FPS:
            continue
        n_try += 1
        best = None
        for name, ser in regions.items():
            ref = ser[r0:r0 + nref]
            if len(ref) < nref:
                continue
            d, sh, sc = xcorr_peak(sig, ref)
            if d is not None and (best is None or sh > best[1]):
                best = (d, sh, sc, name)
        if best is None:
            continue
        d, sh, sc, name = best
        rel = d / FPS - margin
        if _accept(rel, sh, sc):
            s["vseek"] = pred + rel
            n_ok += 1
            if verbose and abs(rel) > 0.08:
                print(f"    [percut] {st}@{a:.1f} ({b-a:.1f}s): {rel:+.3f}s "
                      f"(sharp {sh:.2f}, score {sc:.2f}, {name})", flush=True)
    if verbose:
        print(f"  [percut] aligned {n_ok}/{n_try} eligible one-shots "
              f"(rest use the global map)", flush=True)
    return n_ok, n_try


def _dense_points(cam_m, tiles, apts, total, step=15.0, w=45.0, margin=6.0,
                  minsharp=1.4):
    """(t, voff) points, trying EVERY composite region per window and keeping
    the sharpest lock. The composite layout is dynamic (tiles reorder, hosts go
    full-screen), so no region is host-bound; when the host isn't on screen at
    all, every candidate fails and the window is skipped -- correct behavior."""
    ax = np.array([p[0] for p in apts]); ay = np.array([p[1] for p in apts])
    nref = int(w * FPS)
    pts, regions = [], []
    t = w / 2
    while t < total - w / 2:
        a = float(np.interp(t, ax, ay))
        r0 = int(round((t - w / 2) * FPS))
        s0 = int(round(((t - w / 2) + a - margin) * FPS))
        best = None
        if s0 >= 0:
            sig = cam_m[s0:s0 + nref + int(2 * margin * FPS)]
            if len(sig) >= nref + FPS:
                for name, tile_m in tiles.items():
                    ref = tile_m[r0:r0 + nref]
                    if len(ref) < nref:
                        continue
                    d, sh, sc = xcorr_peak(sig, ref)
                    if d is not None and sh >= minsharp and (best is None or sh > best[1]):
                        best = (d, sh, name)
        if best:
            pts.append((float(t), float(a + (best[0] / FPS - margin))))
            regions.append(best[2])
        t += step
    return pts, regions


CACHE_VER = 3   # bump when the measurement scheme changes (invalidates caches)


def build_maps(comp, cams, cache_dir, step=15.0, verbose=True):
    """cams: {host_label: camera_path}. Returns {host: (voff_fn, info)}.
    Caches measured points in <cache_dir>/vmap_<host>.json."""
    total = None
    tiles = None        # decoded lazily, shared across hosts (one comp pass)
    out = {}
    _series_out = {}    # freshly-decoded motion series -> persisted for percut
    for host, cam in cams.items():
        cache = os.path.join(cache_dir, f"vmap_{host}.json")
        if os.path.exists(cache):
            d = json.load(open(cache))
            if (d.get("ver") == CACHE_VER and d.get("cam") == os.path.basename(cam)
                    and d.get("video_points")):
                po, info = syncfit.fit_from_points(
                    [tuple(p) for p in d["video_points"]], 0.0, d["total"],
                    verbose=verbose, label=f"video:{host}(cache)", both_dirs=True)
                out[host] = (po, info)
                if verbose:
                    print(f"  [vidsync] {host}: cached ({len(d['video_points'])} pts)", flush=True)
                continue
        if total is None:
            import subprocess
            total = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", comp]).strip())
        if tiles is None:
            if verbose: print("  [vidsync] decoding composite regions (one pass)...", flush=True)
            tiles = motion_series(comp, TILE, "comp")
            _series_out.update({f"comp_{k}": v for k, v in tiles.items()})
        if verbose: print(f"  [vidsync] {host}: audio anchor points...", flush=True)
        apts = audio_points(cam, comp, total, step=120.0)
        if len(apts) < 2:
            if verbose: print(f"  [vidsync] {host}: no audio lock, skipping", flush=True)
            out[host] = (None, {"error": "no audio anchors"})
            continue
        if verbose: print(f"  [vidsync] {host}: decoding camera...", flush=True)
        cam_m = motion_series(cam, CAMBOX, f"cam:{host}")
        _series_out[f"cam_{host}"] = cam_m
        pts, regions = _dense_points(cam_m, tiles, apts, total, step=step)
        if len(pts) < 2:
            out[host] = (None, {"error": "too few confident video points"})
            continue
        po, info = syncfit.fit_from_points(pts, 0.0, total, verbose=verbose,
                                           label=f"video:{host}", both_dirs=True)
        ax = np.array([p[0] for p in apts]); ay = np.array([p[1] for p in apts])
        drift = [(t, v - float(np.interp(t, ax, ay))) for (t, v) in pts]
        json.dump({"ver": CACHE_VER, "cam": os.path.basename(cam),
                   "comp": os.path.basename(comp), "host": host, "total": total,
                   "audio_points": apts, "video_points": pts, "drift": drift,
                   "regions": regions, "splices": info["splices"]},
                  open(cache, "w"), indent=1)
        if verbose:
            rv = [r for _, r in drift]
            from collections import Counter
            print(f"  [vidsync] {host}: {len(pts)} pts, regions {dict(Counter(regions))}, "
                  f"video-audio drift median {np.median(rv):+.3f}s "
                  f"range [{min(rv):+.3f},{max(rv):+.3f}]", flush=True)
        out[host] = (po, info)
    if _series_out:
        sp = os.path.join(cache_dir, SERIES_FILE)
        old = load_series(cache_dir) or {}
        old.update(_series_out)
        np.savez_compressed(sp, **old)
        if verbose:
            print(f"  [vidsync] motion series cached -> {sp}", flush=True)
    return out
