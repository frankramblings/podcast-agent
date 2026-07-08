#!/usr/bin/env python3
"""
wistia-pull-feeds — download the individual ISO record streams (per-participant
feeds) for a Wistia recording, by replaying the private GraphQL "bulk download"
flow the web UI uses. The public Data API / MCP does NOT expose these; this is
the only way to get tim/frank/composite as separate files programmatically.

Reverse-engineered from the manage-page HAR (2026-06-30). Flow:
  1. mutation bulkDownloadRecordStreams(mediaId)  -> backgroundJob id
  2. poll  backgroundJobStatus(id) until terminal -> firstDownloadUrl (.zip)
  3. GET the zip, unzip into <out>/<hashed_id>/

Auth: needs a logged-in browser SESSION COOKIE for <subdomain>.wistia.com.
The CSRF token rotates per request, so we scrape a fresh one from the manage
page HTML each run — you only ever supply the (long-lived) session cookie.

Get the cookie ONCE: in the Wistia web UI, DevTools > Network > any request to
your-account.wistia.com > right-click > Copy as cURL, and grab the big
-H 'cookie: ...' value. Save it to secrets/wistia_cookie.txt (one line) or pass
--cookie. Refresh only when it stops working (logout / long idle).

Usage:
  python3 bin/wistia-pull-feeds.py <hashed_id> [--account SUB] [--out DIR]
                                   [--cookie-file PATH | --cookie STR]
                                   [--url-only]   # just print the zip URL, don't download
Example:
  python3 bin/wistia-pull-feeds.py 3tw0b9s6iz --account frankramblings
"""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error, zipfile, io, subprocess

MUT = ("mutation BulkDownloadRecordStreams($input: BulkDownloadRecordStreamsInput!) {\n"
       "  bulkDownloadRecordStreams(input: $input) {\n    backgroundJobStatus {\n"
       "      id\n      __typename\n    }\n    __typename\n  }\n}")
STATUS = ("query BulkDownloadStatus($id: ID!) {\n  backgroundJobStatus(id: $id) {\n"
          "    id\n    terminal\n    status\n    backgroundJobObject {\n      __typename\n      id\n"
          "      ... on MediaDownload {\n        firstDownloadUrl\n        hasMultipleDownloadUrls\n"
          "        __typename\n      }\n    }\n    __typename\n  }\n}")


def gid_for(hashed_id: str) -> str:
    """Wistia Relay global id: base64('Types::VideoType-<hashed_id>')."""
    return base64.b64encode(f"Types::VideoType-{hashed_id}".encode()).decode()


def http(url, *, data=None, headers=None, method=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.getcode(), r.read(), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), dict(ex.headers or {})


CSRF_Q = ("query checkAuthorizationStatusQuery($afterLoginRedirectUrl: Url!) {\n"
          "  currentAuthenticityToken\n"
          "  contentManagementAuthorizationStatus(afterLoginRedirectUrl: $afterLoginRedirectUrl) {\n"
          "    __typename\n  }\n}")


def scrape_csrf(base, cookie, hashed):
    """Mint a fresh Rails authenticity token via the bootstrap GraphQL query.
    This query needs only the session cookie (no CSRF), and also tells us
    whether the cookie is still authorized."""
    redirect = f"{base}/medias/{hashed}/manage"
    headers = {"content-type": "application/json", "cookie": cookie,
               "origin": base, "referer": f"{base}/", "user-agent": "Mozilla/5.0"}
    code, body, _ = http(f"{base}/graphql?op=checkAuthorizationStatusQuery",
                         data=json.dumps({"operationName": "checkAuthorizationStatusQuery",
                                          "variables": {"afterLoginRedirectUrl": redirect},
                                          "query": CSRF_Q}).encode(),
                         headers=headers, method="POST")
    try:
        d = json.loads(body)["data"]
    except Exception:
        return None
    status = (d.get("contentManagementAuthorizationStatus") or {}).get("__typename")
    if status and status != "AuthorizationStatusAllowed":
        return None  # cookie no longer authorized
    return d.get("currentAuthenticityToken")


def gql(base, cookie, csrf, op, payload):
    headers = {"content-type": "application/json", "x-csrf-token": csrf, "cookie": cookie,
               "origin": base, "referer": f"{base}/", "user-agent": "Mozilla/5.0"}
    code, body, _ = http(f"{base}/graphql?op={op}", data=json.dumps(payload).encode(),
                         headers=headers, method="POST")
    try:
        return code, json.loads(body)
    except Exception:
        return code, body[:400].decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hashed_id")
    ap.add_argument("--account", default=os.environ.get("WISTIA_ACCOUNT", "frankramblings"))
    ap.add_argument("--out", default="media/wistia-feeds")
    ap.add_argument("--cookie")
    ap.add_argument("--cookie-file", default="secrets/wistia_cookie.txt")
    ap.add_argument("--csrf", help="override CSRF instead of scraping")
    ap.add_argument("--url-only", action="store_true")
    ap.add_argument("--poll", type=float, default=2.0)
    ap.add_argument("--max-polls", type=int, default=120)
    a = ap.parse_args()

    cookie = a.cookie or os.environ.get("WISTIA_COOKIE")
    if not cookie and os.path.exists(a.cookie_file):
        cookie = open(a.cookie_file).read().strip()
    if not cookie:
        sys.exit(f"No session cookie. Save it to {a.cookie_file} or pass --cookie. See header of this script.")

    base = f"https://{a.account}.wistia.com"

    csrf = a.csrf or scrape_csrf(base, cookie, a.hashed_id)
    if not csrf:
        sys.exit("Could not scrape CSRF token — cookie likely expired/invalid. Refresh it.")

    # 1. kick off
    code, res = gql(base, cookie, csrf, "BulkDownloadRecordStreams",
                    {"operationName": "BulkDownloadRecordStreams",
                     "variables": {"input": {"mediaId": gid_for(a.hashed_id)}}, "query": MUT})
    if code != 200 or not isinstance(res, dict) or res.get("errors"):
        sys.exit(f"mutation failed (HTTP {code}): {res}")
    job = res["data"]["bulkDownloadRecordStreams"]["backgroundJobStatus"]["id"]
    print(f"[1/3] export job started: {job[:24]}…", file=sys.stderr)

    # 2. poll
    url = None
    for i in range(a.max_polls):
        code, res = gql(base, cookie, csrf, "BulkDownloadStatus",
                        {"operationName": "BulkDownloadStatus", "variables": {"id": job}, "query": STATUS})
        s = res["data"]["backgroundJobStatus"]
        print(f"[2/3] poll {i}: {s['status']}", file=sys.stderr)
        if s["terminal"]:
            if s["status"] != "FINISHED":
                sys.exit(f"job ended non-OK: {s['status']}")
            url = s["backgroundJobObject"]["firstDownloadUrl"]
            break
        time.sleep(a.poll)
    if not url:
        sys.exit("timed out waiting for export")

    if a.url_only:
        print(url); return

    # 3. download the zip with a RESUMABLE, retrying transfer. These bundles are
    # multi-GB; the old single-shot urllib stream died on any hiccup (the ~333 MB
    # truncation bug). curl -C - resumes a partial file; rerun to continue.
    outdir = os.path.join(a.out, a.hashed_id)
    os.makedirs(outdir, exist_ok=True)
    zip_path = os.path.join(outdir, "_feeds.zip")
    print(f"[3/3] downloading zip -> {zip_path} (resumable) …", file=sys.stderr)
    rc = subprocess.call(["curl", "-fL", "-C", "-", "--retry", "8",
                          "--retry-all-errors", "--retry-delay", "2",
                          "-H", f"cookie: {cookie}", "-A", "Mozilla/5.0",
                          "-o", zip_path, url])
    if rc != 0:
        sys.exit(f"zip download failed (curl exit {rc}); rerun this command to resume from {zip_path}")
    # verify integrity before trusting it (catches a truncated/partial bundle)
    if subprocess.call(["unzip", "-tq", zip_path]) != 0:
        sys.exit(f"zip is incomplete/corrupt: {zip_path} — rerun to resume the download")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(outdir)
        names = zf.namelist()
    os.remove(zip_path)
    print(f"extracted {len(names)} files -> {outdir}", file=sys.stderr)
    for n in names:
        print(os.path.join(outdir, n))


if __name__ == "__main__":
    main()
