#!/usr/bin/env python3
"""
Tonight's-episode driver for the Director (BwG jdcxvxzvdm, 2026-06-30).

Repoints the render_full / render_full2 sync+grammar pipeline at tonight's feeds.
This episode is structurally SIMPLER than the Jun 23 spike: Frank's camera did
NOT drop, so instead of 4 native chunks he arrives as one continuous feed. We
therefore model Frank as a single "chunk" spanning [0, total] with its own
GCC-PHAT offset, and let Tim's linear fit + the composite clock work unchanged.

Everything else (competitive gate, shot grammar, dynamic two-shot, frame-exact
assembly) is reused verbatim from render_full2.

Usage:
    python3 render_tonight.py --a 0 --b 120 --out tonight_proof.mp4
"""
import sys, argparse
import render_full as rf
import render_full2 as rf2

FEEDS = "/home/frank/.openclaw/workspace/media/wistia-feeds/jdcxvxzvdm"
COMP  = f"{FEEDS}/composite_main.mp4"
TIM   = f"{FEEDS}/Clip 1 - Tim - camera - 00h00m03s to 00h49m06s - 7wkhyo1mem.mp4"
FRANK = f"{FEEDS}/Clip 1 - Frank - camera - 00h00m03s to 00h49m06s - ss73k0cvbt.mp4"

def repoint():
    total = rf.dur(COMP)
    # Frank = one continuous chunk across the whole episode.
    chunks = [{"start": 0.0, "end": total, "path": FRANK, "off": None}]
    for mod in (rf, rf2):
        mod.COMP = COMP
        mod.TIM = TIM
        mod.CHUNKS = chunks
    # render output dir -> tonight's feeds folder, not real/
    rf.R = FEEDS
    return total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=float, default=0.0)
    ap.add_argument("--b", type=float, default=120.0)
    ap.add_argument("--out", default="tonight_proof.mp4")
    ap.add_argument("--floor", type=float, default=-45.0)
    ap.add_argument("--overlap", type=float, default=9.0)
    ap.add_argument("--min-gap", type=float, default=12.0)
    ap.add_argument("--two-len", type=float, default=1.6)
    ap.add_argument("--react-margin", type=float, default=10.0)
    ap.add_argument("--react-min", type=float, default=0.2)
    args = ap.parse_args()

    total = repoint()
    print(f"[tonight] composite={total:.1f}s  window=[{args.a},{args.b}]", flush=True)

    # hand the parsed args straight to rf2.main via argv, so all its
    # sync/gate/grammar/assembly logic runs untouched against the repointed globals.
    sys.argv = ["render_full2.py",
                "--a", str(args.a), "--b", str(args.b), "--out", args.out,
                "--floor", str(args.floor), "--overlap", str(args.overlap),
                "--min-gap", str(getattr(args, "min_gap")), "--two-len", str(args.two_len),
                "--react-margin", str(args.react_margin), "--react-min", str(args.react_min)]
    rf2.main()

if __name__ == "__main__":
    main()
