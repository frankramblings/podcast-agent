#!/usr/bin/env python3
"""
Chunk-aware validation render. Frank's camera = 4 native chunks, each placed at
its filename composite-timecode, each with its OWN constant offset (no stitched-
backup seams). For a window, resolve which chunk covers it, measure that chunk's
offset the SAME way the confirmed-good path did (envelope best_lag, seek at +off),
and render a switched clip. Same sign convention as Option A.

Windows chosen to hit chunk 0 (control), chunk 2 (was drifting), chunk 3 (past
the 38:24 seam where the backup's worst step lived).
"""
import os, subprocess, json
from offset import envelope, best_lag, ENV_HZ
from gate import decode_pcm, rms_db_track, decide, smooth
from render_real import grammar, assemble
from chunks import parse_chunks

R = "real"
COMP = f"{R}/composite.mp4"; TIM = f"{R}/tim_cam.mp4"
CLIP = 45.0; FPS = 30.0
CHUNKS = parse_chunks()
WINDOWS = [180, 1020, 2400]   # chunk0 / chunk2 / chunk3 (past seam)

def run(c): return subprocess.run(c, capture_output=True, text=True)

def find_chunk(t0):
    for c in CHUNKS:
        if c["start"] <= t0 and t0+CLIP <= c["end"]:
            return c
    return None

def env_offset(ref_path, ref_at, probe_path, probe_at, span=120, maxlag=8):
    ref = envelope(ref_path, ref_at-15, span)
    pr  = envelope(probe_path, probe_at-15, span)
    L, c = best_lag(ref, pr, int(maxlag*ENV_HZ))
    return L/ENV_HZ, c

results = []
for i, t0 in enumerate(WINDOWS):
    ch = find_chunk(t0)
    if not ch:
        print(f"[win {i}] t0={t0}s -> in a GAP, no Frank chunk; skip"); continue
    ci = CHUNKS.index(ch)
    flocal = t0 - ch["start"]
    foff, fc = env_offset(COMP, t0, ch["path"], flocal)
    toff, tc = env_offset(COMP, t0, TIM, t0)
    print(f"[win {i}] t0={t0}s chunk{ci} flocal={flocal:.1f}s  FRKoff={foff:+.2f}(c{fc:.2f})  TIMoff={toff:+.2f}(c{tc:.2f})", flush=True)
    comp_s=f"{R}/cc{i}_comp.mp4"; tim_v=f"{R}/cc{i}_tim.mp4"; frk_v=f"{R}/cc{i}_frk.mp4"
    frk_a=f"{R}/cc{i}_frk.wav"; tim_a=f"{R}/cc{i}_tim.wav"
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{t0:.3f}","-t",f"{CLIP}","-i",COMP,
         "-c:v","libx264","-preset","veryfast","-c:a","aac",comp_s])
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{t0+toff:.3f}","-t",f"{CLIP}","-i",TIM,
         "-an","-c:v","libx264","-preset","veryfast",tim_v])
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{flocal+foff:.3f}","-t",f"{CLIP}","-i",ch["path"],
         "-an","-c:v","libx264","-preset","veryfast",frk_v])
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{flocal+foff:.3f}","-t",f"{CLIP}","-i",ch["path"],
         "-vn","-ac","1","-ar","44100",frk_a])
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{t0+toff:.3f}","-t",f"{CLIP}","-i",TIM,
         "-vn","-ac","1","-ar","44100",tim_a])
    fr = rms_db_track(decode_pcm(frk_a,8000,None,None),8000,0.05)
    tm = rms_db_track(decode_pcm(tim_a,8000,None,None),8000,0.05)
    n = min(len(fr),len(tm)); fr,tm = fr[:n],tm[:n]
    states = smooth(decide(fr,tm,-45.0,6.0),5)
    segs = grammar(states,0.05,FPS,1.2,0.6)
    out = f"{R}/cclip_{i}_{t0}s.mp4"
    assemble(segs,{"frank":frk_v,"tim":tim_v,"composite":comp_s},comp_s,FPS,out)
    air = {}
    for s in segs: air[s["stream"]]=round(air.get(s["stream"],0)+s["end"]-s["start"],1)
    print(f"  -> {out}  shots={len(segs)} airtime={air}", flush=True)
    rep = max(segs,key=lambda s:s["end"]-s["start"]); t=(rep["start"]+rep["end"])/2
    lbl = f"t={t0//60:.0f}min {rep['stream'].upper()} chunk{ci} Foff{foff:+.1f}"
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{t:.3f}","-i",out,
         "-vf",f"drawtext=text='{lbl}':x=24:y=24:fontsize=40:fontcolor=yellow:box=1:boxcolor=black@0.6",
         "-frames:v","1",f"{R}/ccs_{i}.png"])
    results.append({"t0":t0,"chunk":ci,"foff":foff,"fc":fc,"toff":toff,"tc":tc,"out":out,"airtime":air})

if len(results)==3:
    run(["ffmpeg","-y","-loglevel","error","-i",f"{R}/ccs_0.png","-i",f"{R}/ccs_1.png","-i",f"{R}/ccs_2.png",
         "-filter_complex","[0][1][2]hstack=3,scale=1500:-1",f"{R}/proof_chunks.png"])
json.dump(results, open(f"{R}/chunk_results.json","w"), indent=2)
print("CHUNKDONE", flush=True)
