#!/usr/bin/env python3
"""Live progress bar for a raw ffmpeg splice → workspace task JSON schema.

Polls the growing output mp4 via ffprobe and writes share/tasks/<id>/progress.json
in the same schema as bin/bwg-progress so the PWA task card can render it.
"""
import sys, os, time, json, subprocess, argparse
from datetime import datetime

WS = os.path.expanduser("~/.openclaw/workspace")

def iso_now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def duration(path):
    try:
        r = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path],
            capture_output=True, text=True, timeout=5)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True, help="ffmpeg PID to watch")
    ap.add_argument("--out", required=True, help="output mp4 being written")
    ap.add_argument("--target", type=float, required=True, help="expected final duration in seconds")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--task-label", default="BwG splice")
    ap.add_argument("--task-kind", default="render")
    ap.add_argument("--publish-to", default=None,
                    help="on success, copy the finished file here and publish share URL")
    ap.add_argument("--share-url", default=None, help="share URL to advertise when done")
    ap.add_argument("--interval", type=float, default=1.0)
    a = ap.parse_args()

    task_dir = f"{WS}/share/tasks/{a.task_id}"
    os.makedirs(task_dir, exist_ok=True)
    session_key = os.environ.get("OPENCLAW_MCP_SESSION_KEY")
    message_id  = os.environ.get("OPENCLAW_MCP_CURRENT_MESSAGE_ID")
    started_iso = iso_now()
    started = time.time()

    def alive(pid):
        try: os.kill(pid, 0); return True
        except OSError: return False

    def write(status, pct, eta, url=None, err=None, detail="encoding"):
        payload = {
            "id":         a.task_id,
            "label":      a.task_label,
            "kind":       a.task_kind,
            "status":     status,
            "pct":        round(pct, 1),
            "detail":     detail,
            "segText":    None,
            "elapsed":    round(time.time() - started, 1),
            "eta":        None if eta is None else round(eta),
            "url":        url,
            "error":      err,
            "sessionKey": session_key,
            "messageId":  message_id,
            "startedAt":  started_iso,
            "updatedAt":  iso_now(),
        }
        path = f"{task_dir}/progress.json"
        tmp  = f"{path}.tmp"
        with open(tmp, "w") as f: json.dump(payload, f)
        os.replace(tmp, path)

    last_reported = 0
    while alive(a.pid):
        cur = duration(a.out)
        pct = 100.0 * cur / a.target if a.target > 0 else 0.0
        elapsed = time.time() - started
        eta = None
        if cur > 0.5:
            eta = elapsed * (a.target - cur) / cur
        write("running", min(pct, 99.0), eta, detail=f"encoding {cur:.0f}s / {a.target:.0f}s")
        last_reported = cur
        time.sleep(a.interval)

    # final ffprobe
    cur = duration(a.out)
    if cur >= a.target * 0.95 and os.path.getsize(a.out) > 1024:
        url = a.share_url
        if a.publish_to:
            os.makedirs(os.path.dirname(a.publish_to), exist_ok=True)
            subprocess.run(["cp", a.out, a.publish_to], check=True)
        write("done", 100.0, 0, url=url, detail="done")
        print(f"✅ done → {url or a.out}")
        return 0
    else:
        write("failed", pct, None, err=f"ffmpeg died at {cur:.1f}s of {a.target:.1f}s target", detail="ffmpeg died")
        print(f"❌ ffmpeg died at {cur:.1f}s / {a.target:.1f}s")
        return 3

if __name__ == "__main__":
    sys.exit(main() or 0)
