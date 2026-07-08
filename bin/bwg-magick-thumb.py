#!/usr/bin/env python3
"""BwG YouTube thumbnail — pure ImageMagick compositing (no Canva calls).

Layout: full-bleed movie key art (background) + tilted yellow box (foreground)
with black bold-italic condensed caps, in the show's Canva-derived house style.
"""
import argparse, subprocess, sys, tempfile, os

W, H = 1280, 720
YELLOW = "#FFDD1F"
FONT = "/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-BoldOblique.otf"

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(" ".join(cmd) + "\n" + r.stderr + "\n")
        raise SystemExit(1)
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", required=True, help="Full-bleed movie key art (any aspect; will center-crop to 1280x720)")
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tilt", type=float, default=-2.5, help="Yellow box rotation, degrees")
    ap.add_argument("--box-w", type=int, default=820)
    ap.add_argument("--box-h", type=int, default=260)
    ap.add_argument("--box-y", type=int, default=490, help="Top-y of yellow box in the frame")
    ap.add_argument("--pointsize", type=int, default=88)
    a = ap.parse_args()

    td = tempfile.mkdtemp(prefix="bwgthumb_")

    # 1) Base: center-crop art to 1280x720
    base = f"{td}/base.jpg"
    run(["magick", a.art, "-gravity", "center",
         "-resize", f"{W}x{H}^", "-crop", f"{W}x{H}+0+0", "+repage", base])

    # 2) Build the yellow box with a distinct offset black shadow-outline (Canva template look)
    box_layer = f"{td}/box.png"
    text = f"{a.line1}\n{a.line2}"
    inner_w = a.box_w - 60
    # Yellow interior + text
    run(["magick", "-size", f"{a.box_w}x{a.box_h}", f"xc:{YELLOW}",
         "-font", FONT, "-fill", "black", "-pointsize", str(a.pointsize),
         "-gravity", "center", "-size", f"{inner_w}x",
         "-annotate", "+0+0", text, box_layer])
    # Add a thick black border ring around the yellow rectangle
    run(["magick", box_layer, "-bordercolor", "black", "-border", "6", box_layer])

    # 3) Rotate the box (transparent background)
    box_rot = f"{td}/box_rot.png"
    run(["magick", box_layer, "-background", "none",
         "-rotate", str(a.tilt), "+repage", box_rot])

    # 4) Drop shadow: black offset copy behind
    shadow = f"{td}/shadow.png"
    run(["magick", box_rot,
         "(", "+clone", "-background", "black", "-shadow", "80x8+10+10", ")",
         "+swap", "-background", "none", "-layers", "merge", "+repage", shadow])

    # 5) Composite over base, centered horizontally, at box_y
    # Determine offset: center the rotated box horizontally, use box_y as top
    # After rotation size grows slightly; use gravity=north and translate
    out = f"{td}/out.jpg"
    x_off = 0
    y_off = a.box_y - 30  # small shim for rotation growth
    run(["magick", base, shadow, "-gravity", "north",
         "-geometry", f"+{x_off}+{y_off}", "-composite",
         "-quality", "88", out])

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    run(["cp", out, a.out])
    print("wrote", a.out)

if __name__ == "__main__":
    main()
