#!/usr/bin/env python3
"""Turn the BwG render's job record into a live progress.json the web page polls.
Interpolates pct/ETA between the render's every-50-shot milestones so the page
moves smoothly every 2s. Faststart-publishes the finished master to share/bwg/."""
import json, os, time, glob, subprocess, re, shutil
from datetime import datetime, timezone

HOME = "/home/frank/.openclaw"
JOBS = f"{HOME}/workspace/tmp/jobs"
SHARE = f"{HOME}/workspace/share/bwg"
FEEDS = f"{HOME}/workspace/media/wistia-feeds/jdcxvxzvdm"
MASTER_SRC = f"{FEEDS}/master_full.mp4"
MASTER_DST = f"{SHARE}/master_full.mp4"
LABEL = "BwG 49-min master"
os.makedirs(SHARE, exist_ok=True)

def find_rec():
    best = None
    for p in glob.glob(f"{JOBS}/*.json"):
        try: r = json.load(open(p))
        except Exception: continue
        if r.get("label") == LABEL:
            if best is None or r.get("_updatedEpoch",0) >= best.get("_updatedEpoch",0):
                best = r
    return best

def iso_epoch(s):
    try: return datetime.fromisoformat(s).timestamp()
    except Exception: return None

published = False
assembly_start = None      # wall time first seg milestone seen
last_real_seg = None       # last integer seg from job detail
last_change_t = None       # when last_real_seg last changed
per_seg = 1.8              # seconds per shot (seeded, then measured)

while True:
    rec = find_rec()
    now = time.time()
    if rec is None:
        json.dump({"status":"running","pct":0,"detail":"starting…","elapsed":0,
                   "ago":"just now","segText":"—"}, open(f"{SHARE}/progress.json","w"))
        time.sleep(2); continue

    started = iso_epoch(rec.get("startedAt","")) or now
    detail = rec.get("detail") or ""
    status = rec.get("status","running")
    m = re.match(r"(\d+)/(\d+)", detail)

    est_pct = rec.get("pct") or 0.0
    seg_text = "—"; eta = None
    if m:
        cur, tot = int(m.group(1)), int(m.group(2))
        seg_text = f"{cur:,} / {tot:,}"
        if assembly_start is None: assembly_start = now
        if last_real_seg is None or cur != last_real_seg:
            if last_real_seg is not None and cur > last_real_seg and last_change_t:
                dt = now - last_change_t
                measured = dt / max(1, cur - last_real_seg)
                per_seg = 0.5*measured + 0.5*per_seg      # smooth
            last_real_seg = cur; last_change_t = now
        # interpolate forward from the last milestone, capped before the next one
        drift = (now - last_change_t) / per_seg if per_seg > 0 else 0
        est_seg = min(cur + 49.0, tot - 0.3, cur + drift)
        est_pct = max(est_pct, min(99.4, est_seg / tot * 100.0))
        eta = int(max(0, (tot - est_seg) * per_seg))

    if m:
        phase = "assembling final cut…"
    elif status == "running":
        phase = "analyzing audio & building shot grammar…"
    else:
        phase = detail or status

    out = {
        "status": status,
        "pct": round(est_pct, 1),
        "detail": phase,
        "segText": seg_text,
        "elapsed": now - started,
        "eta": eta,
        "ago": "just now",
        "error": rec.get("error"),
        "masterReady": False,
    }

    if status == "done":
        out["pct"] = 100.0; out["eta"] = 0
        if not published and os.path.exists(MASTER_SRC):
            try:
                subprocess.run(["ffmpeg","-y","-i",MASTER_SRC,"-c","copy",
                                "-movflags","+faststart",MASTER_DST],
                               check=True, capture_output=True)
                published = True
            except Exception:
                try: shutil.copy(MASTER_SRC, MASTER_DST); published = True
                except Exception: pass
        out["masterReady"] = published or os.path.exists(MASTER_DST)

    json.dump(out, open(f"{SHARE}/progress.json","w"))

    if status in ("done","failed"):
        if status=="failed" or out["masterReady"]:
            time.sleep(5); break
    time.sleep(2)
