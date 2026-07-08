---
name: "podcast-publish"
description: "End-to-end podcast episode pipeline: pull feeds, render, transcript-driven edit, generate text + thumbnail, schedule to audio host + YouTube. Show-agnostic."
status: proposal
version: "v1"
date: "2026-07-08T03:59:05.264Z"
---

# podcast-publish

Use when the user says "let's edit the latest \<show\>", "ship episode N", "publish this to \<host\> and YouTube", or walks a recording from raw feeds to scheduled release. Show-agnostic — configuration lives in `bin/<show>/`.

## Phase gates (do NOT skip; each is a checkpoint)

### 1. INGEST
- Confirm three things BEFORE pulling: **(1)** source hashed ID, **(2)** renumber policy if slotting between existing scheduled eps, **(3)** cadence weekday.
- Pull feeds via the show's puller (e.g. `bin/wistia-pull-feeds.py <id>` for Wistia-sourced shows).
- **Composite = whatever the user says it is, not a filename regex.** If the puller returns only iso/participant tracks (no `*composite*.mp4`), STOP and ask for a composite URL/path. Never guess. Accept an explicit URL override (e.g. `https://<host>/s/<id>`) as first-class input and download it into the feeds dir with a `composite` prefix.

### 2. RENDER
- Always **proof render first** (`--proof`), verify-gate, then full render.
- **Progress card default ON** for any encode/render >30s: write to `share/tasks/<task-id>/progress.json` so the PWA shows a live card. Never default to "ping when it lands."
- If the wrapper's log-tail hangs past `DYNDONE`, kill only the tailer (not the whole wrapper) and proceed to verify.

### 3. EDIT (transcript-driven)
- Pull the episode transcript from the source host (Wistia has a `/transcript` endpoint; other hosts: whisper API fallback).
- **Hook selection** — propose 1 recommended + 2 alts with exact timestamps and full quote. Wait for user pick before cutting.
- **Front trim** — silencedetect + first-word check; leave ~0.4s of natural head, never clip the first word.
- **Tail trim** — silencedetect the sign-off word; cut to exactly 1s after.
- **Internal cuts default to HARD JUMP.** Crossfade only for the front hook→episode splice or when user explicitly asks. Do not smooth over content edits with crossfades.
- **Preview before render**: print `IN: <t>, OUT: <t>, first-3-words: "...", last-3-words: "..."` for each segment so the user can catch a bad boundary before the ~10 min re-encode.

### 4. ASSETS

**Text — audio host (Fireside-style):**
- Title = a **funny non-sequitur pulled from the transcript** (BwG convention; per-show may differ).
- **Do NOT prefix with episode number** — most audio hosts number automatically. Just the phrase (e.g. `Magic Jungle Potion`, not `Ep 567: Magic Jungle Potion`).
- Full show notes, chapters, tags, keywords.

**Text — YouTube:**
- Title = **algo-shaped, not descriptive**. Prefer negation/curiosity hooks, ≤60 chars, front-loaded searched keyword.
- Description: front-load searched keyword phrase in first 150 chars, then chapters formatted for YT auto-detect (`0:00 Title`), then tags-reordered high-volume first.
- Pinned comment draft saved but expect API `forbidden` on scheduled videos — user pins manually post-publish.

**Thumbnail (Canva MCP):**
- **The MCP DOES support headless editing.** Pipeline:
  1. `copy-design` from show's template
  2. `start-editing-transaction(design_id)` → txn_id + `richtexts` + `fills` with element_ids
  3. `upload-asset-from-url` for new hero art → asset id
  4. `perform-editing-operations(transaction_id, page_index=1, operations)` — `replace_text` for text, `update_fill(asset_type:"image", alt_text:...)` for the top-most editable image fill
  5. `commit-editing-transaction` → `export-design(format:{type:"jpg",quality:95})`
  6. Download signed URL, publish to media server
- `page_index` is **1-indexed**.
- Text overlay: ≤3 words for mobile legibility, match YT title's hook.

### 5. SCHEDULE
- Compute release date from **cadence weekday + last scheduled episode** (not "today + 7"). Weekly Wednesdays = next Wed after last scheduled ep's date.
- Verify all currently-staged episodes align with the cadence rule; if any drift, batch-fix them in one pass.
- Match publish time across hosts (audio + YT) so subscribers see them drop together.

### 6. SHIP

**Audio host:** API path preferred. Puppeteer only as fallback. Verify draft UUID matches the intended episode (not a stale slug from a prior run).

**YouTube:** **Try API upload FIRST** (`google-api-nodejs-client`). Puppeteer/Chrome-profile path fails the moment the Google session lapses.
1. `videos.insert` (resumable) with metadata + `privacyStatus: private`
2. `videos.update` → `privacyStatus: scheduled` + `publishAt: <ISO>`
3. `thumbnails.set` with the Canva-rendered jpg
4. Attempt pinned comment; on `forbidden`, save text and tell user to pin manually.

### 7. VERIFY (post-ship checklist — do NOT skip)
- Audio host: title has no accidental episode-number prefix, date is correct, banner reads "Scheduled".
- YouTube: URL loads, scheduled time matches, thumbnail is the Canva one (not YT auto-frame), chapters render.
- Sanity-check adjacent staged episodes: did we accidentally overwrite a live episode's draft slot?

## Per-show config (target contract — not yet implemented)
Each show would live in `bin/<show>/` with:
- `config.json` — cadence weekday, publish time, hosts (audio + video ids), title conventions, thumbnail template design id
- `content_<N>.json` — per-episode text assets

## Common failure modes (observed, fixed)
1. **Composite filename assumption** — accept explicit override.
2. **Front-trim clipped hook** — print IN/OUT + first-3-words preview.
3. **Crossfade smoothed content cut** — hard-jump default for internal edits.
4. **Canva "not supported" amnesia** — transaction pattern works.
5. **Puppeteer-before-API for YouTube** — API is durable.
6. **Fireside title had `Ep N:` prefix** — platform numbers automatically.
7. **Progress amnesia** — PWA progress card default for long renders.
8. **Cadence drift on staged eps** — recompute all when inserting/renumbering.

## Related memories
These name private workspace memories that are not part of this repo:
bwg-episode-pipeline, fireside-automation, canva-mcp-wired,
wistia-iso-feed-download, durable-media-server.