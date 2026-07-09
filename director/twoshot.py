#!/usr/bin/env python3
"""
Dynamic Director (v2) — pepper the two-shot in tastefully, AutoPod-style.

Reuses the validated v1 sync model (per-chunk Frank offsets, Tim linear fit,
composite clock) from assemble. The ONLY change is the grammar: instead of a
pure who's-loudest one-shot machine, it layers three two-shot behaviors. Two-shot
== composite, which is always in sync, so dynamism costs zero sync risk.

Knobs (all CLI):
  --overlap      dB: both above floor and within this of each other -> two-shot.
  --min-gap      s : breather two-shot becomes eligible this long after the last
                     one, then fires at the next natural pause.
  --two-len      s : length of an inserted two-shot.
  --react-margin dB / --react-min s: the listener above floor+margin for at
                     least this long during a solo -> reaction two-shot.
  --floor        dBFS speech floor.

Usage:
  twoshot.py --a 1000 --b 1240 --out dyn_test.mp4
  twoshot.py --a 0 --b 0 --out master_dynamic.mp4
"""
import os, subprocess, tempfile, json, argparse, shutil, atexit
import numpy as np
import assemble
from chunks import pcm, gcc_phat, SR
from gate import decode_pcm, rms_db_track, smooth
from shot_grammar import grammar

# episode state (COMP/TIM/CHUNKS/R) is read off the assemble module at call
# time so assemble.configure() reaches both layers; only true constants copy.
HOP = assemble.HOP; FPS = assemble.FPS

def run(c): return subprocess.run(c, capture_output=True, text=True)

def gate_energy(a, b, toff_fn, frank_src=None, frank_seek=None):
    """Raw dB tracks (fr, tm) on the composite clock; Frank silence in gaps."""
    span = b - a; nf = int(round(span / HOP))
    tmp = tempfile.mkdtemp(prefix="ge_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    tw = f"{tmp}/t.wav"
    run(["ffmpeg","-y","-loglevel","error","-ss",f"{a+toff_fn(a):.3f}","-t",f"{span:.3f}",
         "-i",assemble.TIM,"-vn","-ac","1","-ar","44100",tw])
    tm = rms_db_track(decode_pcm(tw,8000,None,None),8000,HOP)
    if frank_src is not None:
        fw = f"{tmp}/f.wav"
        run(["ffmpeg","-y","-loglevel","error","-ss",f"{frank_seek:.3f}","-t",f"{span:.3f}",
             "-i",frank_src,"-vn","-ac","1","-ar","44100",fw])
        fr = rms_db_track(decode_pcm(fw,8000,None,None),8000,HOP)
    else:
        fr = []
    def fix(x):
        x = list(x[:nf])
        if len(x) < nf: x += [-120.0]*(nf-len(x))
        return x
    return fix(fr), fix(tm)

def classify(fr, tm, floor, overlap):
    out = []
    for f, t in zip(fr, tm):
        if f <= floor and t <= floor:      out.append("nobody")
        elif f > floor and t > floor and abs(f-t) <= overlap: out.append("both")
        elif f >= t:                        out.append("frank")
        else:                               out.append("tim")
    return out

def interject(states, fr, tm, floor, react_margin, react_min, two_len):
    """During a solo, if the OTHER person audibly reacts (laugh/mm-hmm) — above
    floor+react_margin for >= react_min — pop a short two-shot on that beat."""
    out = states[:]; n = len(out)
    rmf = max(1, int(react_min/HOP)); tlf = max(1, int(two_len/HOP))
    hits = 0; i = 0
    while i < n:
        st = out[i]
        if st in ("frank","tim"):
            j = i
            while j < n and out[j] == st: j += 1
            other = tm if st == "frank" else fr
            k = i
            while k < j:
                if other[k] > floor + react_margin:
                    b = k
                    while b < j and other[b] > floor + react_margin: b += 1
                    if b - k >= rmf:
                        c = (k + b)//2
                        s0 = max(i, c - tlf//2); s1 = min(j, c + tlf//2)
                        for x in range(s0, s1): out[x] = "both"
                        hits += 1
                    k = b
                else:
                    k += 1
            i = j
        else:
            i += 1
    return out, hits

def breather(states, fr, tm, min_gap, two_len, floor, quiet_margin=6.0, hard_mult=2.4):
    """Tasteful, not metronomic. A two-shot becomes ELIGIBLE only after min_gap
    since the last one, then FIRES at the next genuine pause (louder mic dips
    near the floor = a breath). If nobody pauses for a long time, force one at
    hard_mult*min_gap so a true monologue still gets a breather. Spacing is
    therefore irregular and every breather lands on a natural beat."""
    out = states[:]; n = len(out)
    gf = max(1, int(min_gap/HOP)); tlf = max(1, int(two_len/HOP))
    hardf = int(min_gap*hard_mult/HOP)
    quiet = floor + quiet_margin
    last = 0; inserted = 0; i = 0
    while i < n:
        if out[i] == "both":
            j = i
            while j < n and out[j] == "both": j += 1
            last = j; i = j; continue
        since = i - last
        if since >= gf and (max(fr[i], tm[i]) < quiet or since >= hardf):
            s0 = i; s1 = min(n, i + tlf)
            for x in range(s0, s1): out[x] = "both"
            inserted += 1; last = s1; i = s1; continue
        i += 1
    return out, inserted

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=float, default=0.0)
    ap.add_argument("--b", type=float, default=0.0)
    ap.add_argument("--out", default="master_dynamic.mp4")
    ap.add_argument("--floor", type=float, default=-45.0)
    ap.add_argument("--overlap", type=float, default=9.0)
    ap.add_argument("--min-gap", type=float, default=12.0)  # min seconds between breather two-shots
    ap.add_argument("--two-len", type=float, default=1.8)
    ap.add_argument("--react-margin", type=float, default=10.0)  # other > floor+this = reaction
    ap.add_argument("--react-min", type=float, default=0.2)
    args = ap.parse_args(argv)

    total = assemble.dur(assemble.COMP)
    A = args.a; B = args.b if args.b > 0 else total
    print(f"window [{A:.1f},{B:.1f}]  overlap={args.overlap}dB min_gap={args.min_gap}s two_len={args.two_len}s", flush=True)

    toff_fn, tf = assemble.tim_fit(total)
    assemble.assemble_full.toff = toff_fn
    print(f"Tim seg0 off(t)={tf[0]:+.5f}*t{tf[1]:+.3f} splices={[round(s) for s in tf[3]]}", flush=True)
    for ch in assemble.CHUNKS:
        ch["off_fn"], finfo = assemble.frank_fit(ch, total)
        mid = (max(ch["start"], A) + min(ch["end"], B)) / 2.0
        ch["off"] = ch["off_fn"](mid)   # scalar approx for energy gating only
        print(f"  chunk {ch['start']}-{ch['end']} off@mid={ch['off']:+.3f} "
              f"splices={[round(s) for s in finfo['splices']]}", flush=True)

    # regions
    regions = []; prev = A
    for ch in assemble.CHUNKS:
        cs, ce = max(ch["start"],A), min(ch["end"],B)
        if cs >= ce: continue
        if cs > prev: regions.append((prev,cs,None))
        regions.append((cs,ce, ch if ch["off"] is not None else None))
        prev = ce
    if prev < B: regions.append((prev,B,None))

    FR, TM = [], []
    for (a,b,ch) in regions:
        if ch is not None:
            fr, tm = gate_energy(a,b,toff_fn,ch["path"],(a-ch["start"])+ch["off"])
        else:
            fr, tm = gate_energy(a,b,toff_fn)
        FR += fr; TM += tm
    n = min(len(FR), len(TM)); FR, TM = FR[:n], TM[:n]

    states = classify(FR, TM, args.floor, args.overlap)
    states = smooth(states, 5)
    n_overlap = states.count("both")
    states, n_react = interject(states, FR, TM, args.floor, args.react_margin, args.react_min, args.two_len)
    states, n_cad = breather(states, FR, TM, args.min_gap, args.two_len, args.floor)
    print(f"two-shot sources: overlap-frames={n_overlap} reaction-beats={n_react} breathers={n_cad}", flush=True)
    segs = grammar(states, HOP, FPS, 1.2, 0.6)
    for s in segs: s["start"] += A; s["end"] += A
    air = {}
    for s in segs: air[s["stream"]] = round(air.get(s["stream"],0)+s["end"]-s["start"],1)
    tot = sum(air.values()) or 1
    pct = {k: f"{100*v/tot:.0f}%" for k,v in air.items()}
    print(f"{len(states)} frames -> {len(segs)} shots; airtime={air} ({pct})", flush=True)
    json.dump({"window":[A,B],"knobs":vars(args),"airtime":air,"segs":segs},
              open(f"{assemble.R}/dyn_cutlist.json","w"), indent=2)
    assemble.assemble_full(segs, A, B, f"{assemble.R}/{args.out}")
    print(f"wrote {assemble.R}/{args.out}", flush=True)
    print("DYNDONE", flush=True)

if __name__ == "__main__":
    main()
