#!/usr/bin/env bash
# One-command deploy: publish this repo to GitHub Pages.
#
#   bash deploy.sh <github-owner>/<repo>
#
# Requirements: git, gh (authenticated), python3.
# What it does:
#   1. refreshes site/data.json (server-side fetch, same code the hourly Action runs)
#   2. commits and pushes
#   3. enables Pages with GitHub Actions as the source
set -euo pipefail

REPO="${1:-}"
if [ -z "$REPO" ]; then
  echo "usage: bash deploy.sh <owner>/<repo>" >&2
  exit 2
fi

cd "$(dirname "$0")"

echo "== fetching data server-side"
python3 scripts/fetch.py

echo "== committing"
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-deploy}" -c user.email="${GIT_AUTHOR_EMAIL:-deploy@example.com}" \
    commit -m "data: refresh $(date -u +%FT%TZ)" || echo "nothing to commit"

echo "== pushing"
git push -u origin HEAD

echo "== enabling Pages (Actions source)"
gh api -X POST "repos/${REPO}/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/${REPO}/pages" -f build_type=workflow >/dev/null 2>&1 \
  || echo "Pages already configured"

echo "done. Site: https://$(echo "$REPO" | cut -d/ -f1).github.io/$(echo "$REPO" | cut -d/ -f2)/"
