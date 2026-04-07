#!/usr/bin/env bash
# Reads config/ci_triggers.json and POSTs repository_dispatch (seps_upstream) for each target.
# Usage: dispatch_downstream.sh <source-repo-short-name>
# Requires: gh, jq, GH_TOKEN or GITHUB_TOKEN with repo scope on target repos.
set -euo pipefail

REPO_KEY="${1:?source repo name, e.g. orchestrator-core}"
ORG="${GITHUB_ORG:-seps-sol}"
ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MAP="$ROOT/config/ci_triggers.json"

export GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "No GH_TOKEN/GITHUB_TOKEN; skip cross-repo dispatch."
  exit 0
fi

if [[ ! -f "$MAP" ]]; then
  echo "No $MAP; skip."
  exit 0
fi

COUNT=$(jq -r --arg k "$REPO_KEY" '.[$k] // [] | length' "$MAP")
if [[ "$COUNT" -eq 0 ]]; then
  echo "No downstream entries for $REPO_KEY"
  exit 0
fi

echo "Dispatch seps_upstream from $ORG/$REPO_KEY → ($COUNT repo(s))"
while IFS= read -r TARGET; do
  [[ -z "$TARGET" ]] && continue
  echo "  → $ORG/$TARGET"
  jq -nc \
    --arg from "$ORG/$REPO_KEY" \
    '{event_type:"seps_upstream",client_payload:{from:$from}}' \
    | gh api --method POST "repos/$ORG/$TARGET/dispatches" --input - || echo "  warn: dispatch failed for $TARGET"
done < <(jq -r --arg k "$REPO_KEY" '.[$k] // [] | .[]' "$MAP")
