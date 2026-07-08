# podcast-agent

Staging ground for a possible product: an autonomous publish agent for
podcasts that already exist.

Not a product yet. Not even close. This repo is a museum of the working
BwG (Beer With Geeks) pipeline, cherry-picked out of Frank's OpenClaw
workspace so we can see it as its own thing before deciding whether to
generalize it.

## What's here

- `bin/bwg` — the orchestrator. `prep | pull | render | verify | share`.
  Runs a real regression gate before it ships a master. Currently
  hardcoded to Frank's workspace paths.
- `bin/wistia-pull-feeds.py` — reverse-engineered Wistia ISO-feed pull
  (GraphQL bulkDownloadRecordStreams + resumable download). Reusable for
  any Wistia-sourced show; needs a session cookie.
- `bin/bwg-prep` — transcript + episode metadata prep.
- `bin/bwg-progress*` — live progress card writer for the workspace PWA.
  Show-agnostic; the "progress.json" contract is portable.
- `bin/bwg-thumbnail.py` / `bin/bwg-canva-thumb.py` — thumbnail generation,
  including the Canva MCP headless-edit pipeline.
- `director/` — the hard IP. Multicam splicer with a lip-sync verification
  gate (EBU R37 tolerance). `verify_video.py` is the gate; `gate.py` is the
  scoring layer; `syncfit.py` / `vidsync*.py` are the alignment core.
- `skills/podcast-publish/SKILL.md` — the show-agnostic phase gates
  (INGEST → RENDER → EDIT → ASSETS → SCHEDULE). This is the closest thing
  to a product spec.

## What's NOT here (intentionally)

- `bin/fireside/` — 80+ per-episode one-shot scripts. Concepts to port,
  not code to keep.
- All `.mp4` / `.mp3` / `.wav` / `.png` / `.log` artifacts.
- Any secrets. `wistia_cookie.txt`, OAuth tokens, MCP session state — none
  of that is here and none of it should ever land here.

## What "ready" looks like

Not ready until a second show runs through this end-to-end in <2 days of
work. Until then, this is a snapshot — do not treat it as canonical. The
canonical copy still lives in `~/.openclaw/workspace/`.
