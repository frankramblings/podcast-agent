# hosts/youtube

Working YouTube uploader, extracted from Frank's BwG workflow.

**State: extracted as-is. `upload.mjs` is the show-agnostic version.**

## Files

- `upload.mjs` — the uploader. Pure YouTube Data API v3 (auth / whoami / upload /
  update / thumb / comment / schedule subcommands). No browser automation — the
  per-episode Puppeteer variants this replaced live only in git history; they were
  exactly the "Puppeteer-before-API" failure mode SKILL.md documents.

## What's hardcoded (must lift into config)

- Channel + video privacy defaults
- Title / description / tags source (probably per-episode `content_<N>_youtube.json`)
- Thumbnail path
- Chapter markers formatted for YT auto-detect (`0:00 Title` lines)
- Scheduled publish time (must match Fireside publish time so subscribers see
  both drop together — SKILL.md phase 5)
- OAuth token / credentials source

## Known quirk from SKILL.md

Pinned-comment API returns `forbidden` on scheduled videos. Draft is saved but
the user pins manually post-publish. Don't try to fix this in code.

## Target shape (not built yet)

```js
uploadEpisode({
  video: '/path/to/master.mp4',
  meta: { title, description, tags, chapters },
  thumbnail: '/path/to/thumb.jpg',
  schedule: { at: '2026-07-15T05:00:00-04:00', privacy: 'private' },
  auth: { tokenPath: '...' },
})
```
