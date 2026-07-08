#!/usr/bin/env python3
"""
Generic BwG episode Director driver. Auto-discovers the feed files in a feeds
dir and repoints the render_full / render_full2 sync+grammar pipeline at them,
modelling Frank as one continuous chunk (uses his *camera backup* when present,
which is continuous even when the front cam dropped into native chunks).

Usage:
    python3 render_ep.py --feeds /path/to/feeds/<id> --out master_<n>.mp4 [--a 0 --b 0]
"""
import sys, glob, os, argparse, subprocess
import render_full as rf
import render_full2 as rf2
import vidsync

def dur(p):
    try:
        return float(subprocess.check_output(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=nk=1:nw=1", p]).decode().strip())
    except Exception:
        return 0.0

def pick(feeds, must, avoid=None):
    """longest .mp4 whose name contains all `must` substrings and none of `avoid`."""
    cands = []
    for p in glob.glob(os.path.join(feeds, "*.mp4")):
        n = os.path.basename(p)
        if all(m in n for m in must) and (not avoid or not any(a in n for a in avoid)):
            cands.append(p)
    if not cands:
        return None
    return max(cands, key=dur)

def discover(feeds):
    comp = pick(feeds, ["composite"]) or pick(feeds, ["composite_main"])
    tim  = pick(feeds, ["Tim", "camera backup"]) or pick(feeds, ["Tim", "camera"])
    # Frank: prefer continuous backup; else longest single Frank camera file
    frank = pick(feeds, ["Frank", "camera backup"]) or pick(feeds, ["Frank", "camera"])
    return comp, tim, frank

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--a", type=float, default=0.0)
    ap.add_argument("--b", type=float, default=0.0)
    ap.add_argument("--floor", type=float, default=-45.0)
    ap.add_argument("--overlap", type=float, default=9.0)
    ap.add_argument("--min-gap", type=float, default=12.0)
    ap.add_argument("--two-len", type=float, default=1.6)
    ap.add_argument("--react-margin", type=float, default=10.0)
    ap.add_argument("--react-min", type=float, default=0.2)
    args = ap.parse_args()

    comp, tim, frank = discover(args.feeds)
    print(f"[ep] COMP={comp}\n[ep] TIM={tim}\n[ep] FRANK={frank}", flush=True)
    if not (comp and tim and frank):
        print("[ep] FATAL: could not discover all three feeds", flush=True)
        sys.exit(2)

    total = rf.dur(comp)
    chunks = [{"start": 0.0, "end": total, "path": frank, "off": None}]
    for mod in (rf, rf2):
        mod.COMP = comp
        mod.TIM = tim
        mod.CHUNKS = chunks
    rf.R = args.feeds

    # video offset maps: place one-shot VIDEO against the composite VIDEO
    # (audio offsets place audio only -- camera video PTS drift vs own audio).
    # Cached in the feeds dir; first build costs a few minutes of decode.
    print("[ep] building video sync maps...", flush=True)
    maps = vidsync.build_maps(comp, {"tim": tim, "frank": frank}, args.feeds)
    tim_v = maps.get("tim", (None, None))[0]
    frank_v = maps.get("frank", (None, None))[0]
    if tim_v:  rf.assemble_full.tim_voff = tim_v
    else:      print("[ep] WARN: no video map for tim; falling back to audio offsets", flush=True)
    if frank_v: chunks[0]["voff_fn"] = frank_v
    else:       print("[ep] WARN: no video map for frank; falling back to audio offsets", flush=True)

    # per-cut alignment: each one-shot's own span re-aligned against the
    # composite (catches short camera freeze/catch-up wobbles the map misses)
    series = vidsync.load_series(args.feeds)
    if series and (tim_v or frank_v):
        preds = {"tim":   (lambda a: a + tim_v(a)) if tim_v else None,
                 "frank": (lambda a: a + frank_v(a)) if frank_v else None}
        rf.assemble_full.percut = lambda segs: vidsync.percut_align(segs, series, preds)
    else:
        print("[ep] WARN: no cached motion series; per-cut alignment disabled", flush=True)
    print(f"[ep] composite={total:.1f}s window=[{args.a},{args.b}]", flush=True)

    sys.argv = ["render_full2.py",
                "--a", str(args.a), "--b", str(args.b), "--out", args.out,
                "--floor", str(args.floor), "--overlap", str(args.overlap),
                "--min-gap", str(getattr(args,"min_gap")), "--two-len", str(args.two_len),
                "--react-margin", str(args.react_margin), "--react-min", str(args.react_min)]
    rf2.main()

if __name__ == "__main__":
    main()
