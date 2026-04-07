#!/usr/bin/env bash
# Shallow clone or fast-forward pull every repository in GITHUB_ORG (default: seps-sol).
set -uo pipefail

ORG="${GITHUB_ORG:-seps-sol}"
ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
DEST="${ORG_REPOS_DIR:-$ROOT/.org-repos}"

mkdir -p "$DEST"
export GH_PROMPT_DISABLED="${GH_PROMPT_DISABLED:-1}"

count=0
while IFS= read -r name; do
  [[ -z "$name" ]] && continue
  full="$ORG/$name"
  target="$DEST/$name"
  if [[ -d "$target/.git" ]]; then
    echo "Pull $full -> $target"
    if ! git -C "$target" pull --ff-only --depth 1 2>/dev/null && ! git -C "$target" pull --depth 1; then
      echo "Warning: pull failed for $full" >&2
    fi
  else
    echo "Clone $full -> $target"
    rm -rf "$target"
    if ! gh repo clone "$full" "$target" -- --depth 1; then
      echo "Warning: clone failed for $full" >&2
    fi
  fi
  count=$((count + 1))
done < <(gh repo list "$ORG" --limit 1000 --json name --jq '.[].name')

if [[ "$count" -eq 0 ]]; then
  echo "No repositories listed for $ORG (check auth and org name)."
fi

echo "Done. Repos under $DEST"
