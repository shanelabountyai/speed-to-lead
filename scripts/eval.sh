#!/usr/bin/env bash
# The eval gate, one command: unit tests (incl. the planted-fabrication gate), then the 40 tuned fixtures and the
# 15 held-out messages each through process-lead on a fresh run log, scored by eval_gate.py. Exits 1 on any failure.
# Live side effects: demo contacts, Gmail drafts and HubSpot tasks (all example.com). It tears down the previous run's first.
# n8n must be stopped (CLI runs clash with a running server on port 5679).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.n8n-runtime/node_modules/.bin:$PATH" N8N_USER_FOLDER="$HOME/.n8n-speed-to-lead"
if lsof -ti :5678 -ti :5679 > /dev/null; then echo "n8n is running: stop it first"; exit 2; fi
out=eval-out; mkdir -p "$out"
step() { echo "-- $1"; shift; "$@" > "$out/step.log" 2>&1 || { echo "FAILED: see $out/step.log"; tail -20 "$out/step.log"; exit 1; }; }

step "unit tests" node --test test/*.test.js
step "generate workflows" sh -c 'python3 scripts/build_phase2.py && python3 scripts/gen_eval_run.py && python3 scripts/gen_eval_run.py holdout'
for f in process-lead dev-eval-run dev-eval-holdout dev-reset-log dev-teardown-hubspot; do step "import $f" n8n import:workflow --input="workflows/$f.json"; done
step "publish process-lead" n8n publish:workflow --id=n1ProcessLead0001
step "teardown previous demo records" n8n execute --id=n1DevTeardownHs01

rc=0
for set in n1-fixtures holdout; do
  id=$([ "$set" = holdout ] && echo n1DevEvalHold001 || echo n1DevEvalRun0001)
  step "reset run log" n8n execute --id=n1ResetLog00001
  echo "-- run $set"
  n8n execute --id="$id" > "$out/$set.txt" 2>&1 || { echo "FAILED: n8n run, see $out/$set.txt"; tail -20 "$out/$set.txt"; exit 1; }
  python3 scripts/eval_gate.py "$out/$set.txt" "$set" | tee "$out/$set.gate.txt"; [ "${PIPESTATUS[0]}" = 0 ] || rc=1
done
echo "EVAL GATE: $([ $rc = 0 ] && echo PASS || echo FAIL)"
exit $rc
