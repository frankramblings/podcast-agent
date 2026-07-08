# hosts/fireside

Working Fireside publisher, extracted from Frank's BwG spike dir.

**State: extracted as-is from ep 567. Needs config lift before it's reusable.**

## Files

- `publish.mjs` — end-to-end flow: login → find-or-create draft → fill fields → schedule → verify. From `ship567.mjs`.
- `login.mjs` — reusable login helper.
- `attach-audio.mjs` — audio-file upload / attachment flow. From `audio565.mjs`.
- `verify.mjs` — post-publish read-back verification. From `verify_final.mjs`.
- `list-episodes.mjs` — episode list scraper.

## What's hardcoded (must lift into a config object)

- Podcast slug: `podcasts/beerwithgeeks/`
- Episode slug + files: `567`, `bwg567.mp3`, `content567.json`
- Host user IDs: `['524','525']` (Frank + Tim on BwG)
- Publish date/time: `2026-07-15 05:00 AM ET`
- Workspace paths: `/home/frank/.openclaw/workspace/bin/fireside/`
- Chrome profile dir + screenshot dir: per-episode
- Auth via env vars `FS_EMAIL` / `FS_PASS`

## Target shape (not built yet)

```js
publishEpisode({
  show: { slug: 'beerwithgeeks', hostIds: ['524','525'] },
  episode: { slug: '567', title: '...', description: '...', chapters: [...] },
  audio: '/path/to/bwg567.mp3',
  schedule: { at: '2026-07-15T05:00:00-04:00' },
  chrome: { profileDir: '...', screenshotDir: '...' },
})
```

Do the lift *after* a second show forces the config surface. Don't design it in a vacuum.
