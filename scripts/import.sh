#!/usr/bin/env bash
# Import the N1 workflows into the project's n8n data folder. n8n must be stopped.
# Imports, then publishes the two spine sub-workflows.
# Usage: ALERT_TO=you@example.com scripts/import.sh
set -euo pipefail
: "${ALERT_TO:?set ALERT_TO to the address that gets error alerts}"
cd "$(dirname "$0")/.."
export PATH="$HOME/.n8n-runtime/node_modules/.bin:$PATH" N8N_USER_FOLDER="$HOME/.n8n-speed-to-lead"
tmp=$(mktemp -d)
for f in workflows/*.json; do sed "s|__ALERT_TO__|$ALERT_TO|g" "$f" > "$tmp/$(basename "$f")"; done
for f in "$tmp"/*.json; do n8n import:workflow --input="$f"; done
rm -rf "$tmp"
# Import leaves workflows unpublished, and a workflow can only call (or be the error workflow of) another once it is published.
for id in n1RunLogWriter01 n1ErrorHandler01; do n8n publish:workflow --id="$id" > /dev/null; done
