#!/usr/bin/env bash
# Import the N1 workflows into the project's n8n data folder. n8n must be stopped.
# Imports, then publishes the two spine sub-workflows.
# Usage: ALERT_TO=you@example.com scripts/import.sh
set -euo pipefail
: "${ALERT_TO:?set ALERT_TO to the address that gets error alerts}"
# ALERT_TO is spliced into workflow JSON by sed: refuse anything that is not a plain address,
# since a quote, backslash, '|' or '&' would corrupt the JSON or the sed replacement.
if ! [[ "$ALERT_TO" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  echo "ALERT_TO is not a plain email address: refusing to import" >&2
  exit 1
fi
cd "$(dirname "$0")/.."
export PATH="$HOME/.n8n-runtime/node_modules/.bin:$PATH" N8N_USER_FOLDER="$HOME/.n8n-speed-to-lead"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for f in workflows/*.json; do sed "s|__ALERT_TO__|$ALERT_TO|g" "$f" > "$tmp/$(basename "$f")"; done
for f in "$tmp"/*.json; do n8n import:workflow --input="$f"; done
# Import leaves workflows unpublished, and a workflow can only call (or be the error workflow of) another once it is published.
for id in n1RunLogWriter01 n1ErrorHandler01; do n8n publish:workflow --id="$id" > /dev/null; done
