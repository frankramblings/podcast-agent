# Credentials

Nothing in this repo contains a secret, and `.gitignore` refuses `secrets/`,
`*cookie*.txt`, `*token*.json`, and `*.env`. Each integration expects its
credential in one of these places at runtime:

## Wistia (feed pulls — `bin/wistia-pull-feeds.py`)

A logged-in browser **session cookie** for a Wistia account with access to the
recordings. Provide via (checked in this order):

1. `--cookie '<cookie header value>'`
2. env `WISTIA_COOKIE`
3. file `secrets/wistia_cookie.txt` relative to the working directory
   (`bin/bwg pull` runs the puller with cwd = `$PODCAST_WS`)

Long-lived; refresh only when it expires. Note the cookie is passed to `curl`
on its command line, so it is visible in local `ps` output while a download
runs — fine for a single-user machine, worth knowing about.

## YouTube (uploads — `hosts/youtube/upload.mjs`)

Pure OAuth, no browser automation. Two files, both relative to the working
directory the script is run from:

1. `secrets/google_oauth_client.json` — a **Desktop app** OAuth client from
   Google Cloud Console (YouTube Data API v3 enabled).
2. `secrets/bwg_youtube_token.json` — written by the script itself:
   `node hosts/youtube/upload.mjs auth` prints a consent URL;
   `node hosts/youtube/upload.mjs auth --code XXX` exchanges and saves the
   refresh token (mode 0600).

## Fireside (publishing — `hosts/fireside/*.mjs`)

Env vars `FS_EMAIL` and `FS_PASS` (the account login). Pipe them from a
password manager rather than exporting them in your shell profile, e.g.
`FS_EMAIL=you@example.com FS_PASS="$(op read op://vault/fireside/password)" node hosts/fireside/publish.mjs`.
