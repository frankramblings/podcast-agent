# podcast-agent

An autonomous publish agent for a podcast that already exists.

One real show ([Beer With Geeks](https://beerwithgeeks.fireside.fm)) ships through
this pipeline: an AI agent pulls the raw multicam recordings, renders an
angle-switched master, makes transcript-driven edits, generates the text assets
and thumbnail, and schedules the release on the audio host and YouTube — behind
phase gates it is not allowed to skip, including a hard lip-sync verification
gate that refuses to ship a master that fails it.

This is the working pipeline extracted as its own thing, not a product.
Everything named `bwg` / `tim` / `frank` is the first show's configuration —
left visible on purpose so you can see exactly what a second show would need
to change.

## The pipeline

    INGEST → RENDER → EDIT → ASSETS → SCHEDULE → SHIP → VERIFY

The agent-facing spec is [`skills/podcast-publish/SKILL.md`](skills/podcast-publish/SKILL.md):
phase gates, human checkpoints, and eight observed-and-fixed failure modes.
The code is what the agent drives at each phase:

| Phase | What happens | Code |
|---|---|---|
| INGEST | Mint + resumable-download per-camera ISO feeds from Wistia (reverse-engineered GraphQL export) | [`bin/wistia-pull-feeds.py`](bin/wistia-pull-feeds.py) |
| RENDER | Audio-driven multicam auto-switch; frame-exact assembly on one global grid (zero cumulative drift) | [`director/render_ep.py`](director/render_ep.py) |
| RENDER gate | GCC-PHAT lip-sync check of the shipped master vs the composite clock, 0.12 s tolerance (EBU R37) | [`director/verify_video.py`](director/verify_video.py) |
| EDIT | Transcript-driven cuts: hook selection, front/tail trims, hard-jump internal edits | agent-executed — SKILL.md phase 3 |
| ASSETS | Transcript + chapters prep; thumbnail compositing | [`bin/bwg-prep`](bin/bwg-prep), [`bin/bwg-thumbnail.py`](bin/bwg-thumbnail.py), [`bin/bwg-magick-thumb.py`](bin/bwg-magick-thumb.py) |
| SCHEDULE + SHIP | Audio host via Puppeteer; YouTube via Data API (upload / thumb / schedule / comment) | [`hosts/fireside/`](hosts/fireside/), [`hosts/youtube/upload.mjs`](hosts/youtube/upload.mjs) |
| VERIFY | Post-ship read-back checks | SKILL.md phase 7 |

Orchestration: [`bin/bwg`](bin/bwg) (`prep | pull | episode | render | verify | test`)
wires render → verify-gate → share, and `bwg test` is a real regression: render a
2-minute window of known-good feeds and require the lip-sync gate to pass.
Long renders write live progress cards ([`bin/bwg-progress`](bin/bwg-progress),
[`bin/bwg-splice-progress.py`](bin/bwg-splice-progress.py)) — a small JSON
contract any dashboard can poll.

## Status — what's real vs scaffolding

| Component | State |
|---|---|
| `director/` | Works; ships weekly. Assumes two hosts (stream names `tim`/`frank`), a 1920×1080 two-tile composite, 30 fps. |
| `bin/bwg` | Works. Data dirs default to `~/.openclaw/workspace`; override with `PODCAST_WS`. |
| `bin/wistia-pull-feeds.py` | Works for any Wistia-sourced show; needs a session cookie ([docs/credentials.md](docs/credentials.md)). |
| `hosts/youtube/upload.mjs` | Works; clean API-only CLI. |
| `hosts/fireside/` | Works but is a browser-automation script hardcoded to one episode's shape — the config lift is deliberately deferred until a second show forces the design. |
| Thumbnails | Work; BwG brand (colors, fonts, wordmark) hardcoded. |
| Canva MCP thumbnail pipeline | Prose-only in SKILL.md phase 4 — not in this repo's code. |
| `skills/podcast-publish/SKILL.md` | Status: proposal. The per-show `config.json` contract it describes is not implemented. |

## Requirements

Nothing here installs itself. You'd need:

- Python 3.8+ with `numpy` (`pip install -r requirements.txt`)
- Node 18+ with `googleapis` + `puppeteer-core` (`npm install`)
- `ffmpeg` / `ffprobe`, ImageMagick 7 (`magick`), Google Chrome (Fireside automation)
- Debian-family URW base35 fonts (thumbnail scripts hardcode their paths)

Credentials (never committed): [docs/credentials.md](docs/credentials.md).
Episode-metadata shapes: `hosts/*/content.example.json`.

## What "ready" would look like

The bar for calling this reusable: a second show runs through it end-to-end in
under two days of work. The known lifts, in rough order: per-show config
(`bin/<show>/config.json` per SKILL.md), de-hardcoding the two-host assumptions
in `director/`, an API path for the audio host, and generalizing the thumbnail
branding. Today it's a working pipeline for one show, shipping weekly.
