#!/usr/bin/env python3
"""
Director spike — the "meat".

Reads isolated mic stems, decides who is speaking over time, applies a small
shot-grammar, then assembles a frame-accurate angle-switched master from N
pre-synced video streams using ffmpeg.

Audio truth = the master bed (default: the composite's audio).
Video = whichever angle the Director picks per segment.

Usage:
    python3 director.py episode.json

This is a throwaway feasibility spike: stdlib + ffmpeg only. No numpy.
"""
import json, os, re, subprocess, sys, tempfile, shutil, atexit

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def probe_duration(path):
    r = run(["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=nk=1:nw=1", path])
    return float(r.stdout.strip())

def speech_intervals(stem, noise_db, min_silence, hangover, duration):
    """Return list of (start,end) where this mic is speaking.
    Uses ffmpeg silencedetect, inverts the silences, then pads each speech
    region by `hangover` at the tail (natural hold after someone stops)."""
    r = run(["ffmpeg","-hide_banner","-nostats","-i",stem,
             "-af",f"silencedetect=noise={noise_db}dB:d={min_silence}",
             "-f","null","-"])
    log = r.stderr
    sil = []
    cur = None
    for line in log.splitlines():
        m = re.search(r"silence_start:\s*([-\d.]+)", line)
        if m: cur = float(m.group(1))
        m = re.search(r"silence_end:\s*([-\d.]+)", line)
        if m and cur is not None:
            sil.append((max(0.0,cur), float(m.group(1)))); cur = None
    if cur is not None:
        sil.append((max(0.0,cur), duration))
    # invert silences -> speech
    speech = []
    t = 0.0
    for s,e in sil:
        if s > t: speech.append((t, s))
        t = max(t, e)
    if t < duration: speech.append((t, duration))
    # tail hangover
    return [(s, min(duration, e + hangover)) for s,e in speech]

def covers(intervals, t):
    return any(s <= t < e for s,e in intervals)

def decide_timeline(cfg, duration):
    g = cfg["grammar"]
    step = 1.0 / cfg["fps"]
    speech = {spk: speech_intervals(path, g["noise_db"], g["min_silence"],
                                    g["hangover"], duration)
              for spk, path in cfg["stems"].items()}
    # sample -> raw decision
    raw = []
    t = 0.0
    while t < duration - 1e-9:
        active = [spk for spk in speech if covers(speech[spk], t)]
        if len(active) == 1:
            stream = cfg["speaker_stream"].get(active[0], cfg["default_stream"])
        elif len(active) >= 2:
            stream = cfg["default_stream"]      # overlap -> widen (2-shot)
        else:
            stream = cfg["default_stream"]      # nobody -> safe wide
        raw.append((round(t,5), stream))
        t += step
    # collapse equal consecutive samples into segments
    segs = []
    for tt, stream in raw:
        if segs and segs[-1]["stream"] == stream:
            segs[-1]["end"] = round(tt + step, 5)
        else:
            segs.append({"stream": stream, "start": round(tt,5),
                         "end": round(tt+step,5)})
    segs[-1]["end"] = duration
    # enforce minimum shot length: merge any too-short segment into a neighbor
    min_shot = g["min_shot"]
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i,s in enumerate(segs):
            if s["end"] - s["start"] < min_shot:
                if i > 0:
                    segs[i-1]["end"] = s["end"]
                else:
                    segs[i+1]["start"] = s["start"]
                segs.pop(i); changed = True; break
    # merge neighbors that ended up on the same stream
    merged = []
    for s in segs:
        if merged and merged[-1]["stream"] == s["stream"]:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(dict(s))
    # frame-snap boundaries and keep contiguous (no gaps/overlap)
    fps = cfg["fps"]
    snap = lambda x: round(round(x*fps)/fps, 6)
    for i,s in enumerate(merged):
        s["start"] = snap(s["start"]) if i>0 else 0.0
        if i>0: s["start"] = merged[i-1]["end"]
        s["end"] = snap(s["end"])
    merged[-1]["end"] = duration
    return merged

def assemble(cfg, segs, outpath):
    streams = cfg["streams"]
    audio_src = cfg.get("audio") or streams[cfg["default_stream"]]
    tmp = tempfile.mkdtemp(prefix="director_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    parts = []
    for i,s in enumerate(segs):
        part = os.path.join(tmp, f"seg_{i:03d}.mp4")
        r = run(["ffmpeg","-y","-loglevel","error",
                 "-i", streams[s["stream"]],
                 "-ss", f'{s["start"]:.3f}', "-to", f'{s["end"]:.3f}',
                 "-an","-c:v","libx264","-pix_fmt","yuv420p",
                 "-r", str(cfg["fps"]), "-vsync","cfr", part])
        if r.returncode != 0:
            print(r.stderr); sys.exit(1)
        parts.append(part)
    listf = os.path.join(tmp,"list.txt")
    with open(listf,"w") as f:
        for p in parts: f.write(f"file '{p}'\n")
    silent = os.path.join(tmp,"silent.mp4")
    run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0",
         "-i",listf,"-c","copy",silent])
    r = run(["ffmpeg","-y","-loglevel","error","-i",silent,"-i",audio_src,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac",
             "-shortest", outpath])
    if r.returncode != 0:
        print(r.stderr); sys.exit(1)

def main():
    cfg_path = sys.argv[1] if len(sys.argv)>1 else "episode.json"
    cfg = json.load(open(cfg_path))
    os.chdir(os.path.dirname(os.path.abspath(cfg_path)) or ".")
    dur = probe_duration(cfg["streams"][cfg["default_stream"]])
    segs = decide_timeline(cfg, dur)
    print(f"duration={dur:.3f}s  fps={cfg['fps']}  -> {len(segs)} shots\n")
    print(f"{'#':>2}  {'stream':<10} {'start':>7} {'end':>7} {'len':>6}")
    for i,s in enumerate(segs):
        print(f"{i:>2}  {s['stream']:<10} {s['start']:>7.2f} {s['end']:>7.2f} "
              f"{s['end']-s['start']:>6.2f}")
    out = cfg.get("out","master.mp4")
    assemble(cfg, segs, out)
    print(f"\nwrote {out}")
    json.dump(segs, open("cutlist.json","w"), indent=2)

if __name__ == "__main__":
    main()
