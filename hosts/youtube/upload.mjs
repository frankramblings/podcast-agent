#!/usr/bin/env node
// BWG YouTube uploader — pure YouTube Data API v3, no browser automation.
// Reuses the desktop OAuth client (secrets/google_oauth_client.json), stores a
// SEPARATE refresh token for the BWG channel so no other Google token is touched.
//
// SSH-friendly consent (localhost redirect that won't load; copy the `code`):
//   node bin/youtube-upload.mjs auth               -> prints consent URL
//   node bin/youtube-upload.mjs auth --code XXX    -> exchanges + saves token
//   node bin/youtube-upload.mjs whoami             -> prints authorized channel
//   node bin/youtube-upload.mjs upload <file> <content.json> [--privacy private|unlisted|public]
//   node bin/youtube-upload.mjs update <videoId> <content.json>   -> patch title/desc/tags of a live video
//
// content.json fields: title, description, keywords (comma str), tag_list (unused).
// Prefer a YOUTUBE-NATIVE metadata file (e.g. *_youtube.json) for both upload+update
// so the channel never gets the podcast RSS copy. See BWG-EPISODE-RUNBOOK.md.
import { google } from 'googleapis';
import fs from 'node:fs';

const CRED  = 'secrets/google_oauth_client.json';
const TOKEN = 'secrets/bwg_youtube_token.json';
const SCOPES = [
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/youtube.force-ssl', // upload + edit/update existing videos
  'https://www.googleapis.com/auth/youtube.readonly',
];

const keys = JSON.parse(fs.readFileSync(CRED, 'utf8'));
const k = keys.installed || keys.web;
const redirect = (k.redirect_uris && k.redirect_uris[0]) || 'http://localhost';

function client(withToken = false) {
  const o = new google.auth.OAuth2(k.client_id, k.client_secret, redirect);
  if (withToken) {
    const t = JSON.parse(fs.readFileSync(TOKEN, 'utf8'));
    o.setCredentials({ refresh_token: t.refresh_token });
  }
  return o;
}

const [cmd, ...rest] = process.argv.slice(2);

if (cmd === 'auth') {
  const ci = rest.indexOf('--code');
  const o = client();
  if (ci === -1) {
    const url = o.generateAuthUrl({ access_type: 'offline', prompt: 'consent', scope: SCOPES });
    console.log('REDIRECT URI:', redirect);
    console.log('\n=== Sign in as beerwithgeeks@gmail.com, approve, then copy the `code` from the localhost URL ===\n');
    console.log(url + '\n');
  } else {
    const code = rest[ci + 1];
    const { tokens } = await o.getToken(code);
    if (!tokens.refresh_token) throw new Error('No refresh_token. Revoke at myaccount.google.com/permissions and retry.');
    fs.writeFileSync(TOKEN, JSON.stringify({
      type: 'authorized_user', client_id: k.client_id, client_secret: k.client_secret,
      refresh_token: tokens.refresh_token,
    }, null, 2), { mode: 0o600 });
    console.log('Saved', TOKEN, '— refresh_token present:', !!tokens.refresh_token);
  }
} else if (cmd === 'whoami') {
  const yt = google.youtube({ version: 'v3', auth: client(true) });
  const { data } = await yt.channels.list({ part: 'snippet', mine: true });
  const ch = data.items?.[0];
  console.log(ch ? `Channel: ${ch.snippet.title} (${ch.id})` : 'No channel found for this account.');
} else if (cmd === 'upload') {
  const [file, contentPath] = rest;
  const privIdx = rest.indexOf('--privacy');
  const privacy = privIdx !== -1 ? rest[privIdx + 1] : 'private';
  if (!file || !contentPath) { console.error('usage: upload <file> <content.json> [--privacy private|unlisted|public]'); process.exit(1); }
  const meta = JSON.parse(fs.readFileSync(contentPath, 'utf8'));
  const tags = (meta.keywords || '').split(',').map(s => s.trim()).filter(Boolean);
  const size = fs.statSync(file).size;
  const yt = google.youtube({ version: 'v3', auth: client(true) });

  console.log(`Uploading ${file} (${(size / 1048576).toFixed(0)} MB) as "${meta.title}" [${privacy}]...`);
  const res = await yt.videos.insert(
    {
      part: 'snippet,status',
      requestBody: {
        snippet: { title: meta.title, description: meta.description, tags, categoryId: '24' }, // 24 = Entertainment
        status: { privacyStatus: privacy, selfDeclaredMadeForKids: false },
      },
      media: { body: fs.createReadStream(file) },
    },
    { onUploadProgress: e => process.stdout.write(`\r  ${((e.bytesRead / size) * 100).toFixed(1)}%   `) }
  );
  console.log(`\n✅ Uploaded: https://youtu.be/${res.data.id}  (status: ${res.data.status.privacyStatus})`);
} else if (cmd === 'thumb') {
  const [videoId, img] = rest;
  if (!videoId || !img) { console.error('usage: thumb <videoId> <image.jpg>'); process.exit(1); }
  const yt = google.youtube({ version: 'v3', auth: client(true) });
  const res = await yt.thumbnails.set({ videoId, media: { body: fs.createReadStream(img) } });
  console.log(`✅ Thumbnail set on https://youtu.be/${videoId}`);
} else if (cmd === 'schedule') {
  // Schedule the video to auto-publish (go public) at an ISO8601 UTC time. Keeps it private until then.
  const [videoId, publishAt] = rest;
  if (!videoId || !publishAt) { console.error('usage: schedule <videoId> <ISO8601-UTC e.g. 2026-07-03T11:00:00Z>'); process.exit(1); }
  const yt = google.youtube({ version: 'v3', auth: client(true) });
  const res = await yt.videos.update({
    part: 'status',
    requestBody: { id: videoId, status: { privacyStatus: 'private', publishAt, selfDeclaredMadeForKids: false } },
  });
  console.log(`✅ Scheduled https://youtu.be/${videoId} to publish at ${res.data.status.publishAt}`);
} else if (cmd === 'comment') {
  // Posts the pinned_comment text from content.json as a top-level comment (pinning itself is Studio-only).
  const [videoId, contentPath] = rest;
  if (!videoId || !contentPath) { console.error('usage: comment <videoId> <content.json>'); process.exit(1); }
  const meta = JSON.parse(fs.readFileSync(contentPath, 'utf8'));
  if (!meta.pinned_comment) { console.error('no pinned_comment field in', contentPath); process.exit(1); }
  const yt = google.youtube({ version: 'v3', auth: client(true) });
  const res = await yt.commentThreads.insert({
    part: 'snippet',
    requestBody: { snippet: { videoId, topLevelComment: { snippet: { textOriginal: meta.pinned_comment } } } },
  });
  console.log(`✅ Comment posted (id ${res.data.id}). Pin it in Studio (1 click — API can't pin).`);
} else if (cmd === 'update') {
  const [videoId, contentPath] = rest;
  if (!videoId || !contentPath) { console.error('usage: update <videoId> <content.json>'); process.exit(1); }
  const meta = JSON.parse(fs.readFileSync(contentPath, 'utf8'));
  const tags = (meta.keywords || '').split(',').map(s => s.trim()).filter(Boolean);
  const yt = google.youtube({ version: 'v3', auth: client(true) });
  // videos.update requires the full snippet incl. categoryId; fetch current to preserve category.
  const cur = await yt.videos.list({ part: 'snippet', id: videoId });
  const snip = cur.data.items?.[0]?.snippet;
  if (!snip) { console.error('Video not found or not owned:', videoId); process.exit(1); }
  const res = await yt.videos.update({
    part: 'snippet',
    requestBody: {
      id: videoId,
      snippet: {
        title: meta.title, description: meta.description, tags,
        categoryId: snip.categoryId, defaultLanguage: snip.defaultLanguage,
      },
    },
  });
  console.log(`✅ Updated https://youtu.be/${res.data.id} — "${res.data.snippet.title}"`);
} else {
  console.log('commands: auth [--code XXX] | whoami | upload <file> <content.json> [--privacy ...] | update <videoId> <content.json> | thumb <videoId> <image.jpg> | comment <videoId> <content.json> | schedule <videoId> <ISO8601-UTC>');
}
