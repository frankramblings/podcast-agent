#!/usr/bin/env python3
"""
Full-episode (or windowed) chunk-aware Director render.

Sync model (all measured via GCC-PHAT, applied as +offset seek, same sign as the
validated clips):
  - Frank: 4 native chunks, each placed at its filename composite-timecode, each
    with its OWN constant offset (median of confident interior probes).
  - Tim:   one continuous feed; linear offset fit across the episode.
  - Composite: its own clock (the shared reference + audio bed).

Gating runs region-by-region on the composite clock. Inside a Frank chunk we gate
his aligned iso vs Tim's aligned iso. In gaps (camera off) Frank is forced silent,
so the grammar can only choose Tim or composite there. States are concatenated on
one clock, grammar -> segments, then each segment is sourced from the correct
original via input-seek (fast + frame-accurate) and concatenated. Audio bed =
composite for the rendered window.

Usage:
    render_full.py --a 0 --b 0 --out master_full.mp4      # full episode (b=0 => end)
    render_full.py --a 420 --b 560 --out seamtest.mp4     # windowed gap-crossing test
"""
import os, subprocess, json, tempfile, sys, argparse, shutil, atexit
import numpy as np
from chunks import parse_chunks, gcc_phat, pcm, SR
from gate import decode_pcm, rms_db_track, decide, smooth
from render_real import grammar
import syncfit

R = "real"
COMP = f"{R}/composite.mp4"; TIM = f"{R}/tim_cam.mp4"
FPS = 30.0; HOP = 0.05
CHUNKS = parse_chunks()

def run(c): return subprocess.run(c, capture_output=True, text=True)

def dur(path):
    r = run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path])
    return float(r.stdout.strip())

def measure(probe_path, probe_at, comp_at, span=90, maxlag=10):
    fr = pcm(probe_path, probe_at, span); cp = pcm(COMP, comp_at, span)
    n = min(len(fr), len(cp))
    if n < SR*5: return None, 0.0
    return gcc_phat(fr[:n], cp[:n], maxlag)

def chunk_offset(ch, minsharp=50):
    d = ch["end"] - ch["start"]
    pts = np.linspace(8, d-8, 5) if d > 30 else [d/2]
    vals = []
    for lt in pts:
        lag, sh = measure(ch["path"], lt, ch["start"]+lt)
        if lag is not None and sh > minsharp: vals.append(lag)
    return float(np.median(vals)) if vals else None

def tim_fit(total, minsharp=50):
    """Splice-aware robust piecewise offset for Tim (was a single least-squares
    line, which tilted through the composite-bed splice and drifted)."""
    po, info = syncfit.fit(measure, TIM, total, step=30, minsharp=minsharp, verbose=True)
    a0, b0 = (info["segs"][0][2], info["segs"][0][3]) if info["segs"] else (0.0, 1.8)
    return po, (a0, b0, info["n"], info.get("splices", []))

def frank_fit(ch, total=None, minsharp=45, step=30):
    """Splice-aware robust piecewise offset for a Frank chunk, measured in the
    chunk's OWN local time but returned as a function of COMPOSITE time (the
    domain src_for evaluates). Frank's camera is 4 native chunks each placed at
    its filename composite-timecode: chunk-local 0 == composite ch['start']. So
    we probe chunk-local `lt` against composite `ch.start+lt` and store points on
    the composite clock. (Was a single constant median -> uniformly-off Frank.)"""
    dur_ch = ch["end"] - ch["start"]
    span = 60.0 if dur_ch >= 90 else max(12.0, dur_ch * 0.5)
    edge = 15.0 if dur_ch >= 90 else max(3.0, dur_ch * 0.15)
    pts = []
    lt = edge
    while lt < dur_ch - edge:
        a = ch["start"] + lt                              # composite time
        lag, sh = measure(ch["path"], lt, a, span=span)   # chunk-local vs composite
        if lag is not None and sh > minsharp:
            pts.append((float(a), float(lag)))
        lt += step
    if len(pts) < 2:                                       # short chunk: center probes
        for f in (0.35, 0.5, 0.65):
            lt = dur_ch * f; a = ch["start"] + lt
            lag, sh = measure(ch["path"], lt, a, span=span)
            if lag is not None and sh > minsharp:
                pts.append((float(a), float(lag)))
    return syncfit.fit_from_points(pts, float(ch["start"]), float(ch["end"]),
                                   verbose=True, label=f"frank@{ch['start']}")

def gate_region(a, b, toff_fn, frank_src=None, frank_seek=None):
    """Return states list of length round((b-a)/HOP). Tim is the clock (always
    present); Frank padded with silence past its available content."""
    span = b - a
    nf = int(round(span / HOP))
    tmp = tempfile.mkdtemp(prefix="gr_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    tw = f"{tmp}/t.wav"
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{a+toff_fn(a):.3f}","-t",f"{span:.3f}",
         "-i",TIM,"-vn","-ac","1","-ar","44100",tw])
    tm = rms_db_track(decode_pcm(tw,8000,None,None),8000,HOP)
    if frank_src is not None:
        fw = f"{tmp}/f.wav"
        run(["ffmpeg","-y","-loglevel","error","-ss",f"{frank_seek:.3f}","-t",f"{span:.3f}",
             "-i",frank_src,"-vn","-ac","1","-ar","44100",fw])
        fr = rms_db_track(decode_pcm(fw,8000,None,None),8000,HOP)
    else:
        fr = []
    # normalize lengths to nf; pad silence
    def fix(x):
        x = list(x[:nf])
        if len(x) < nf: x += [-120.0]*(nf-len(x))
        return x
    tm = fix(tm); fr = fix(fr)
    return decide(fr, tm, -45.0, 6.0)

def src_for(seg, toff_fn):
    """VIDEO seek for a one-shot. Prefers the vidsync video map (voff) over the
    audio offset: camera-backup files stamp video as gapless CFR even when the
    capture dropped frames, so video PTS drifts vs the file's own audio by a
    time-varying amount (>2s measured on 566). Audio offsets place AUDIO only."""
    st = seg["stream"]; a = seg["start"]
    if st == "tim":
        vf = getattr(assemble_full, "tim_voff", None)
        return TIM, a + (vf(a) if vf else toff_fn(a))
    if st == "frank":
        for ch in CHUNKS:
            if ch["start"] <= a < ch["end"]:
                if ch.get("voff_fn"):                 # continuous feed only
                    return ch["path"], (a - ch["start"]) + ch["voff_fn"](a)
                off = ch["off_fn"](a) if ch.get("off_fn") else ch["off"]
                return ch["path"], (a - ch["start"]) + off
        return COMP, a
    return COMP, a

def assemble_full(segs, A, B, out):
    # per-cut video alignment: seg['vseek'] overrides the map-derived seek for
    # one-shots (short camera-timeline wobbles the 45s-window map can't see)
    percut = getattr(assemble_full, "percut", None)
    if percut:
        percut(segs)
    tmp = tempfile.mkdtemp(prefix="rf_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    parts = []
    vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
          "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%g" % FPS)
    # Frame-EXACT assembly: each segment gets an integer frame count on a single
    # global grid (frames since A), so the parts sum to exactly the audio length
    # with ZERO cumulative rounding drift. This is what keeps sync from slipping
    # over a long continuous render.
    acc = 0
    for i, s in enumerate(segs):
        src, seek = src_for(s, assemble_full.toff)
        if s.get("vseek") is not None:
            seek = s["vseek"]
        end_frame = int(round((s["end"] - A) * FPS))
        nf = end_frame - acc            # exact frames this segment must contribute
        acc = end_frame
        if nf <= 0: continue
        p = os.path.join(tmp, f"s{i:04d}.mp4")
        r = run(["ffmpeg","-y","-loglevel","error","-ss",f"{seek:.3f}",
                 "-i",src,"-an","-vf",vf,"-c:v","libx264","-preset","veryfast",
                 "-pix_fmt","yuv420p","-r",str(FPS),"-vsync","cfr",
                 "-frames:v",str(nf),p])
        if r.returncode: print("SEG FAIL",i,r.stderr[:300]); sys.exit(1)
        parts.append(p)
        if i % 50 == 0: print(f"  seg {i}/{len(segs)}", flush=True)
    lst = os.path.join(tmp, "l.txt")
    open(lst,"w").write("".join(f"file '{p}'\n" for p in parts))
    silent = os.path.join(tmp, "sil.mp4")
    run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,"-c","copy",silent])
    bed = os.path.join(tmp, "bed.m4a")
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{A:.3f}","-t",f"{B-A:.3f}","-i",COMP,
         "-vn","-c:a","aac","-b:a","192k",bed])
    main_mp4 = os.path.join(tmp, "main.mp4")
    r = run(["ffmpeg","-y","-loglevel","error","-i",silent,"-i",bed,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-shortest",main_mp4])
    if r.returncode: print("MUX FAIL",r.stderr[:300]); sys.exit(1)

    # --- Cold-open guard -------------------------------------------------------
    # The composite bed (our audio + anchor) starts ~off_tim(0)s LATE: composite
    # t=0 maps to Tim-cam t=off_tim(0), so Tim's "hi, and welcome to Beer with
    # Geeks" (which lives in the camera pre-roll before composite t=0) is clipped.
    # When rendering from the top, prepend that pre-roll from Tim's camera, using
    # TIM'S CAMERA AUDIO (the composite doesn't contain it), then the composite
    # bed continues seamlessly (both share Tim's voice at the seam).
    if getattr(assemble_full, "cold_open", True) and A <= 0.5:
        intro_off = assemble_full.toff(0.0)     # Tim-cam AUDIO time at composite t=0
        pre = 0.4                                # start a hair before the "H"
        # video drifts vs audio inside the camera file (see src_for): the
        # pre-roll's video is cut at the VIDEO map position, audio at the AUDIO
        # position, and both are cut to the SAME duration D computed UP FRONT
        # from the stream geometry. Never seek before the video stream's first
        # frame and never trust the encoded file's container duration -- seeks
        # into the pre-stream zone make the CFR filter pad unpredictable frame
        # counts (569 came out 0.6s short, 570 came out 1.0s LONG).
        tvf = getattr(assemble_full, "tim_voff", None)
        v_end = tvf(0.0) if tvf else intro_off
        r = run(["ffprobe","-v","error","-select_streams","v",
                 "-show_entries","stream=start_time","-of","csv=p=0",TIM])
        try: v_stream0 = float(r.stdout.strip())
        except ValueError: v_stream0 = 0.0
        D = min(intro_off - pre, v_end - v_stream0 - 0.1)
        nfr = int(D * FPS)                      # exact frames, like the main assembly
        D = nfr / FPS
        if D > 0.5:
            intro = os.path.join(tmp, "intro.mp4")
            iv = os.path.join(tmp, "intro_v.mp4"); ia = os.path.join(tmp, "intro_a.m4a")
            r = run(["ffmpeg","-y","-loglevel","error","-ss",f"{v_end - D:.3f}",
                     "-i",TIM,"-an","-vf",vf,"-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",
                     "-r",str(FPS),"-vsync","cfr","-frames:v",str(nfr),iv])
            r2 = run(["ffmpeg","-y","-loglevel","error","-ss",f"{intro_off - D:.3f}","-t",f"{D:.3f}",
                      "-i",TIM,"-vn","-c:a","aac","-b:a","192k","-ar","44100","-ac","2",ia])
            if r.returncode or r2.returncode:
                print("INTRO FAIL",(r.stderr or r2.stderr)[:300]); sys.exit(1)
            r = run(["ffmpeg","-y","-loglevel","error","-i",iv,"-i",ia,
                     "-map","0:v:0","-map","1:a:0","-c","copy","-shortest",intro])
            if r.returncode:
                print("INTRO FAIL",r.stderr[:300]); sys.exit(1)
            cl = os.path.join(tmp, "cl.txt")
            open(cl,"w").write(f"file '{intro}'\nfile '{main_mp4}'\n")
            r = run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",cl,
                     "-c","copy",out])
            if r.returncode:   # param mismatch fallback: re-encode the join
                r = run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",cl,
                         "-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p","-r",str(FPS),
                         "-c:a","aac","-b:a","192k",out])
            if r.returncode: print("COLDOPEN CONCAT FAIL",r.stderr[:300]); sys.exit(1)
            print(f"  cold-open: prepended Tim pre-roll audio [{intro_off - D:.2f}..{intro_off:.2f}]s "
                  f"video [{v_end - D:.2f}..{v_end:.2f}]s ({D:.2f}s, {nfr} frames)", flush=True)
            return
    shutil.move(main_mp4, out)   # /tmp and real/ may be separate fs (shutil imported at module top)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=float, default=0.0)
    ap.add_argument("--b", type=float, default=0.0)   # 0 => composite end
    ap.add_argument("--out", default="master_full.mp4")
    args = ap.parse_args()
    total = dur(COMP)
    A = args.a; B = args.b if args.b > 0 else total
    print(f"composite duration {total:.1f}s; rendering window [{A:.1f}, {B:.1f}]", flush=True)

    toff_fn, tf = tim_fit(total)
    print(f"Tim linear fit: off(t) = {tf[0]:+.5f}*t {tf[1]:+.3f}  (n={tf[2]} pts)", flush=True)
    assemble_full.toff = toff_fn

    for ch in CHUNKS:
        if ch["end"] <= A or ch["start"] >= B:      # skip chunks outside window
            ch["off_fn"] = None; ch["off"] = None; continue
        ch["off_fn"], finfo = frank_fit(ch)
        mid = (max(ch["start"], A) + min(ch["end"], B)) / 2.0
        ch["off"] = ch["off_fn"](mid)               # scalar approx, gating only
        print(f"  chunk {ch['start']}-{ch['end']}s  off@mid={ch['off']:+.3f} "
              f"splices={[round(s) for s in finfo['splices']]}", flush=True)

    # regions within [A,B], walking chunk/gap structure
    regions = []
    prev = A
    for ch in CHUNKS:
        cs, ce = max(ch["start"], A), min(ch["end"], B)
        if cs >= ce: continue
        if cs > prev: regions.append((prev, cs, None))
        regions.append((cs, ce, ch if ch["off"] is not None else None))
        prev = ce
    if prev < B: regions.append((prev, B, None))

    states = []
    for (a, b, ch) in regions:
        if ch is not None:
            fseek = (a - ch["start"]) + ch["off"]
            st = gate_region(a, b, toff_fn, ch["path"], fseek)
            tag = f"chunk@{ch['start']}"
        else:
            st = gate_region(a, b, toff_fn)
            tag = "GAP/none"
        print(f"  region [{a:.1f},{b:.1f}] {tag}: {len(st)} frames", flush=True)
        states += st

    states = smooth(states, 5)
    segs = grammar(states, HOP, FPS, 1.2, 0.6)
    # shift segment times to absolute composite by adding A (grammar starts at 0)
    for s in segs:
        s["start"] += A; s["end"] += A
    air = {}
    for s in segs: air[s["stream"]] = round(air.get(s["stream"],0)+s["end"]-s["start"],1)
    print(f"{len(states)} frames -> {len(segs)} shots; airtime={air}", flush=True)
    json.dump({"window":[A,B],"tim_fit":tf[:3],
               "chunk_offsets":[(c['start'],c['end'],c['off']) for c in CHUNKS],
               "segs":segs}, open(f"{R}/full_cutlist.json","w"), indent=2)
    assemble_full(segs, A, B, f"{R}/{args.out}")
    print(f"wrote {R}/{args.out}", flush=True)
    print("FULLDONE", flush=True)

if __name__ == "__main__":
    main()
