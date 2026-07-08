# hosts/youtube

Working YouTube uploader, extracted from Frank's BwG workflow.

**State: extracted as-is. `upload.mjs` is the show-agnostic version; the two
per-episode variants are kept as reference until the config surface stabilizes.**

## Files

- `upload.mjs` — the generalized uploader.
- `upload-566.mjs`, `upload-567.mjs` — per-episode variants. Compare against
  `upload.mjs` when lifting the config surface to see which knobs actually vary
  in practice.

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
