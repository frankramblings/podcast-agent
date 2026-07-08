#!/usr/bin/env python3
"""BwG YouTube thumbnail generator (1280x720).

Two-host template: pulls a frame per host from the master, composites them
side-by-side, and overlays a movie/topline, a verdict line, an episode badge,
and the BEER WITH GEEKS wordmark. Deterministic + branded + repeatable so the
pipeline emits a thumbnail per episode.

Usage:
  bin/bwg-thumbnail.py --master share/bwg/master_full.mp4 --out share/bwg/thumb_565.jpg \
    --ep 565 --topline SUPERGIRL --verdict "LIKED IT, DIDN'T LOVE IT" \
    --left-ts 240 --right-ts 2400

Frame timestamps pick the host shots; eyeball a contact sheet and pass good ones.
"""
import argparse, subprocess, tempfile, os, sys

FONT = "/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf"      # topline/badge
FONT_HEAVY = "/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf"      # verdict (wider, punchier)
AMBER = "#FFB000"   # beer
INK   = "#0d1117"
W, H  = 1280, 720

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(" ".join(cmd) + "\n" + r.stderr + "\n")
        raise SystemExit(1)
    return r

def frame(master, ts, out):
    # fast input seek — deterministic per (file, ts) via keyframe snap; accurate seek is too slow deep in a 49-min file
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(ts), "-i", master,
         "-frames:v", "1", "-vf", "scale=1280:720", out])

def panel(src, out, xoff=0):
    # center-crop a 640x720 vertical slice (xoff shifts the crop horizontally)
    run(["magick", src, "-gravity", "center", "-crop", f"640x720+{xoff}+0", "+repage", out])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ep", required=True)
    ap.add_argument("--topline", required=True)
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--left-ts", type=float, required=True)
    ap.add_argument("--right-ts", type=float, required=True)
    ap.add_argument("--left-xoff", type=int, default=0)
    ap.add_argument("--right-xoff", type=int, default=0)
    a = ap.parse_args()

    td = tempfile.mkdtemp(prefix="bwgthumb_")
    fl, fr = f"{td}/l.jpg", f"{td}/r.jpg"
    pl, pr = f"{td}/pl.jpg", f"{td}/pr.jpg"
    frame(a.master, a.left_ts, fl)
    frame(a.master, a.right_ts, fr)
    panel(fl, pl, a.left_xoff)
    panel(fr, pr, a.right_xoff)

    base = f"{td}/base.png"
    # side-by-side hosts + amber center divider
    run(["magick", pl, pr, "+append", "-resize", f"{W}x{H}!", base])
    run(["magick", base, "-fill", AMBER, "-draw", f"rectangle 636,0 644,{H}", base])

    # legibility gradients: darken bottom (verdict) and a touch of top (topline)
    grad = f"{td}/grad.png"
    run(["magick", "-size", f"{W}x{H}", "gradient:none-black", "-gravity", "south",
         "-crop", f"{W}x300+0+0", "+repage", grad])
    run(["magick", base, grad, "-gravity", "south", "-composite", base])
    tgrad = f"{td}/tgrad.png"
    run(["magick", "-size", f"{W}x220", "gradient:black-none", tgrad])
    run(["magick", base, tgrad, "-gravity", "north", "-compose", "over",
         "-define", "compose:args=60", "-composite", base])

    out = a.out
    # TOPLINE (amber, condensed, top-left)
    run(["magick", base, "-font", FONT, "-pointsize", "112",
         "-stroke", "black", "-strokewidth", "6", "-fill", AMBER,
         "-gravity", "northwest", "-annotate", "+28+14", a.topline, out])
    # VERDICT — solid white, heavy font, real drop shadow (punchy, not hollow)
    txt = f"{td}/txt.png"
    run(["magick", "-background", "none", "-font", FONT_HEAVY, "-pointsize", "104",
         "-fill", "white", "-stroke", "black", "-strokewidth", "4",
         "-gravity", "center", "-size", f"{W-90}x", f"caption:{a.verdict}", txt])
    shadow = f"{td}/shadow.png"
    run(["magick", txt, "-background", "black",
         "(", "+clone", "-background", "black", "-shadow", "100x8+0+0", ")",
         "+swap", "-background", "none", "-layers", "merge", "+repage", shadow])
    run(["magick", out, shadow, "-gravity", "south", "-geometry", "+0+30", "-composite", out])

    # EPISODE BADGE (amber disc, top-right, black number)
    run(["magick", out,
         "-fill", AMBER, "-stroke", "black", "-strokewidth", "5",
         "-draw", "circle 1180,90 1180,158",
         "-font", FONT, "-pointsize", "58", "-stroke", "none", "-fill", "black",
         "-gravity", "northwest", "-annotate", f"+{1180-46}+{90-34}", a.ep, out])

    # WORDMARK (bottom-left, letterspaced, subtle)
    run(["magick", out, "-font", FONT, "-pointsize", "34", "-fill", "white",
         "-stroke", "black", "-strokewidth", "3", "-kerning", "4",
         "-gravity", "southwest", "-annotate", "+30+24", "BEER WITH GEEKS", out])

    # ensure < 2MB, 1280x720 jpg
    run(["magick", out, "-resize", f"{W}x{H}!", "-quality", "88", out])
    print("wrote", out)

if __name__ == "__main__":
    main()
