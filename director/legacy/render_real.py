#!/usr/bin/env python3
"""
Apply shot-grammar to competitive-gate states and render a real angle-switched
master from the three synced streams.

    python3 render_real.py gate.json --frank A.mp4 --tim B.mp4 --composite C.mp4
                           --fps 30 --min-shot 1.2 --hangover 0.6 --out master.mp4

who -> stream:  frank->frank cam, tim->tim cam, both/nobody->composite (safe wide).
Audio bed = composite (carries both mics).
"""
import json, os, subprocess, sys, tempfile, argparse, shutil, atexit

def run(c): return subprocess.run(c, capture_output=True, text=True)

def grammar(states, hop, fps, min_shot, hangover):
    # 1) who -> stream, with tail hangover (hold the speaker briefly after they stop)
    stream = []
    for s in states:
        stream.append("composite" if s in ("both","nobody") else s)
    # hangover: extend a solo speaker over following nobody frames
    hframes = int(round(hangover/hop))
    i = 0
    while i < len(stream):
        if stream[i] in ("frank","tim"):
            who = stream[i]; j = i+1
            while j < len(stream) and stream[j] == who: j += 1
            # fill up to hframes of trailing composite-from-nobody with `who`
            k = j; filled = 0
            while k < len(stream) and stream[k] == "composite" and filled < hframes \
                  and (k>=len(states) or states[k]=="nobody"):
                stream[k] = who; k += 1; filled += 1
            i = k
        else:
            i += 1
    # 2) collapse to segments
    segs = []
    for idx, st in enumerate(stream):
        t = idx*hop
        if segs and segs[-1]["stream"] == st: segs[-1]["end"] = t+hop
        else: segs.append({"stream":st,"start":t,"end":t+hop})
    # 3) enforce min shot: merge too-short into previous (or next if first)
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i,s in enumerate(segs):
            if s["end"]-s["start"] < min_shot:
                if i>0: segs[i-1]["end"] = s["end"]
                else:   segs[i+1]["start"] = s["start"]
                segs.pop(i); changed = True; break
    # 4) merge same-stream neighbors
    merged = []
    for s in segs:
        if merged and merged[-1]["stream"]==s["stream"]: merged[-1]["end"]=s["end"]
        else: merged.append(dict(s))
    # 5) frame snap, contiguous
    snap = lambda x: round(round(x*fps)/fps,6)
    for i,s in enumerate(merged):
        s["start"] = 0.0 if i==0 else merged[i-1]["end"]
        s["end"] = snap(s["end"])
    return merged

def assemble(segs, streams, audio, fps, out):
    tmp = tempfile.mkdtemp(prefix="rr_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    parts = []
    for i,s in enumerate(segs):
        p = os.path.join(tmp,f"s{i:03d}.mp4")
        vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
              "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,"
              f"fps={fps}")
        r = run(["ffmpeg","-y","-loglevel","error","-i",streams[s["stream"]],
                 "-ss",f'{s["start"]:.3f}',"-to",f'{s["end"]:.3f}',
                 "-an","-vf",vf,"-c:v","libx264","-preset","veryfast",
                 "-pix_fmt","yuv420p","-r",str(fps),"-vsync","cfr",p])
        if r.returncode: print(r.stderr); sys.exit(1)
        parts.append(p)
    lst = os.path.join(tmp,"l.txt")
    open(lst,"w").write("".join(f"file '{p}'\n" for p in parts))
    silent = os.path.join(tmp,"sil.mp4")
    run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,"-c","copy",silent])
    r = run(["ffmpeg","-y","-loglevel","error","-i",silent,"-i",audio,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-shortest",out])
    if r.returncode: print(r.stderr); sys.exit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gate"); ap.add_argument("--frank",required=True)
    ap.add_argument("--tim",required=True); ap.add_argument("--composite",required=True)
    ap.add_argument("--fps",type=float,default=30.0)
    ap.add_argument("--min-shot",type=float,default=1.2)
    ap.add_argument("--hangover",type=float,default=0.6)
    ap.add_argument("--out",default="master_real.mp4")
    a = ap.parse_args()
    g = json.load(open(a.gate)); hop = g["hop"]; states = g["states"]
    segs = grammar(states, hop, a.fps, a.min_shot, a.hangover)
    streams = {"frank":a.frank,"tim":a.tim,"composite":a.composite}
    print(f"{len(states)} frames -> {len(segs)} shots")
    print(f"{'#':>2} {'stream':<10}{'start':>8}{'end':>8}{'len':>7}")
    tally = {}
    for i,s in enumerate(segs):
        ln=s["end"]-s["start"]; tally[s["stream"]]=tally.get(s["stream"],0)+ln
        print(f"{i:>2} {s['stream']:<10}{s['start']:>8.2f}{s['end']:>8.2f}{ln:>7.2f}")
    print("airtime:", {k:round(v,1) for k,v in tally.items()})
    assemble(segs, streams, a.composite, a.fps, a.out)
    json.dump(segs, open("cutlist_real.json","w"), indent=2)
    print(f"wrote {a.out}")

if __name__ == "__main__":
    main()
