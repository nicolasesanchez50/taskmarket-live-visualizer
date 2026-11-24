#!/usr/bin/env bash
# One-command deploy: publish this repo to GitHub Pages.
#
#   GH_TOKEN=<token> bash deploy.sh <github-owner>/<repo>
#
# Requirements: git, python3 (stdlib only), and a GitHub token with `repo` +
# `workflow` scope in GH_TOKEN. Deliberately does NOT use `gh`: a locally
# configured gh identity can silently differ from the account you mean to
# deploy as, and a deploy must never ride someone else's credential.
#
# What it does:
#   1. refreshes site/data.json (the same server-side fetch the hourly Action runs)
#   2. commits and pushes
#   3. enables Pages with GitHub Actions as the build source
set -euo pipefail

REPO="${1:-}"
if [ -z "$REPO" ]; then
  echo "usage: GH_TOKEN=<token> bash deploy.sh <owner>/<repo>" >&2
  exit 2
fi
if [ -z "${GH_TOKEN:-}" ]; then
  echo "GH_TOKEN is not set. Create a token with repo+workflow scope and re-run." >&2
  exit 2
fi

cd "$(dirname "$0")"

echo "== fetching data server-side"
python3 scripts/fetch.py

echo "== rendering share card"
python3 scripts/share.py || echo "   (share card skipped: headless Chrome or Pillow unavailable)"

echo "== committing"
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-deploy}" -c user.email="${GIT_AUTHOR_EMAIL:-deploy@example.com}" \
    commit -m "data: refresh $(date -u +%FT%TZ)" || echo "   nothing to commit"

echo "== pushing"
git push "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" HEAD:main

echo "== enabling Pages (Actions source)"
REPO="$REPO" python3 - <<'PY'
import json, os, urllib.error, urllib.request

repo = os.environ["REPO"]
token = os.environ["GH_TOKEN"]
url = f"https://api.github.com/repos/{repo}/pages"
body = json.dumps({"build_type": "workflow"}).encode()
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "taskmarket-visualizer-deploy",
}

for method in ("POST", "PUT"):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("   pages:", r.status, json.loads(r.read()).get("html_url"))
            break
    except urllib.error.HTTPError as exc:
        if exc.code == 409:          # already enabled
            print("   pages: already configured")
            break
        if method == "PUT":
            print(f"   pages: {exc.code} {exc.read()[:200]!r}")
            raise SystemExit(1)
        continue
PY

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
echo "done. Site: https://${OWNER}.github.io/${NAME}/"
echo "the hourly refresh runs from .github/workflows/deploy.yml; nothing else to schedule."
