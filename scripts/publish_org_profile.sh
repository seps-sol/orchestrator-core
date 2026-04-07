#!/usr/bin/env bash
# Pushes .github-org-readme/profile/README.md to github.com/$GITHUB_ORG/.github (org profile README).
# Skips API write if base64 content matches GitHub (no empty commits).
set -euo pipefail

ORG="${GITHUB_ORG:-seps-sol}"
REPO="$ORG/.github"
ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
FILE="$ROOT/.github-org-readme/profile/README.md"

export GH_PROMPT_DISABLED="${GH_PROMPT_DISABLED:-1}"

if [[ ! -f "$FILE" ]]; then
  echo "Missing $FILE" >&2
  exit 1
fi

if ! gh repo view "$REPO" --json name >/dev/null 2>&1; then
  echo "Creating $REPO …"
  gh repo create "$REPO" --public --description "Organization profile README for $ORG" || true
fi

content_b64=$(base64 <"$FILE" | tr -d '\n\r ')

if resp=$(gh api "repos/$REPO/contents/profile/README.md" 2>/dev/null); then
  # API may insert newlines in base64; strip whitespace before compare
  remote_b64=$(echo "$resp" | jq -r '.content // empty' | tr -d '\n\r ')
  sha=$(echo "$resp" | jq -r '.sha // empty')
  if [[ "$remote_b64" == "$content_b64" ]]; then
    echo "Org profile README unchanged; skipping commit."
    exit 0
  fi
  if [[ -z "$sha" || "$sha" == "null" ]]; then
    echo "Unexpected API response for profile README." >&2
    exit 1
  fi
  gh api -X PUT "repos/$REPO/contents/profile/README.md" \
    -f message="Sync org profile README from orchestrator-core" \
    -f content="$content_b64" \
    -f sha="$sha"
else
  gh api -X PUT "repos/$REPO/contents/profile/README.md" \
    -f message="Add org profile README" \
    -f content="$content_b64"
fi

echo "Published https://github.com/$REPO/blob/main/profile/README.md"
