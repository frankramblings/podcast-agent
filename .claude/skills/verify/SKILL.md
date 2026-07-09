---
name: verify
description: "End-to-end verification for this repo: run the bwg regression (render golden feeds + lip-sync gate) and require GREEN."
---

# verify

One command exercises the whole render path end-to-end:

    ./bin/bwg test

It imports every director module, renders the opening 120s of the golden
feeds through `render_ep` → `twoshot` → `assemble`, then runs the
`verify_video` lip-sync gate and requires PASS (worst lag ≤ 0.12s).

Requirements:

- Golden feeds at `$PODCAST_WS/media/wistia-feeds/44njfqvjjv`
  (`PODCAST_WS` defaults to `~/.openclaw/workspace`; see `bin/bwg`).
- `ffmpeg`/`ffprobe`, Python 3 + numpy.

Takes ~5 minutes; video sync maps are cached in the feeds dir after the
first build. Success marker: `🟢 GREEN — pipeline renders and passes lip-sync`.

Standalone gate on an existing master:

    ./bin/bwg verify <feeds_dir> <master.mp4>
