# Next

Status: PRD drafted and fixtures written (2026-10-01). No workflow built yet.

1. Phase 1, the spine: triggers (polling), idempotency, error path, run log. No model calls.
2. Phase 2: extraction, scoring, routing, HubSpot write, cost per run.
3. Phase 3: draft reply and approval.
4. Phase 4: eval gate, setup doc, capstone demo.

Decided 2026-10-01: a real lead carrying an injected instruction gets a contact (scored and routed from what it honestly states), no draft, and a review row.

Phase 1 setup done 2026-10-05:
- `npx n8n@2.27.5` FAILS on Node 26 (`isolated-vm` native build; n8n needs Node >=22.22 and <26). Run it under a local Node 22 instead: n8n is installed in `~/.n8n-runtime` (`node@22` + `n8n@2.27.5`). Start: `PATH=$HOME/.n8n-runtime/node_modules/.bin:$PATH N8N_USER_FOLDER=$HOME/.n8n-speed-to-lead n8n start`, editor at http://localhost:5678.
- Confirmed in 2.27.5: Gmail Trigger (labelIds filter), HubSpot + HubSpot Trigger, Google Sheets, Anthropic nodes all present.
- `~/.n8n` was last used by n8n 2.41.5, so launching 2.27.5 recorded a downgrade. It held 0 workflows. Backup: `~/.n8n-backup-2026-10-05`. Decided 2026-10-05: this project uses its own data folder `~/.n8n-speed-to-lead` (fresh, 2.27.5 only); `~/.n8n` is left untouched.

Wired 2026-10-05 (ids, no secrets): run-log sheet `Speed-to-Lead Run Log`, id `1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY` (tabs `runs`, `review`). n8n data is in `~/.n8n-speed-to-lead/.n8n/`. Credentials: Gmail `GGGxY4DRdE9giH2x`, Sheets `McOy4auCNkFX0Os2`; HubSpot not yet added. Gmail has no lead label yet; the inbox is real (10k messages), so the trigger must filter on a dedicated label only.

Built 2026-10-05 (in `workflows/`, import with `ALERT_TO=<addr> scripts/import.sh` while n8n is stopped; the script substitutes the alert address so it never lands in git):
- `run-log-writer` (sub-workflow, appends to `runs`), `error-handler` (alert email, throttled to one per 15 min, then logs), `intake-phase1` (schedule 1 min, Gmail label `n1-lead` = `Label_2`, reads `runs`, skips messages already logged non-error, stub where Phase 2 goes, writes `spine_ok`), `init-headers` (run once; already run, headers verified).
- Design choice: intake uses Schedule + Gmail getAll and dedupes against the sheet, not the Gmail Trigger. The trigger advances its cursor even when a run fails, so a failed lead would never be re-polled. This way anything not logged is picked up again, including mail that arrived while n8n was off.
- Verified: headers in both tabs, intake runs clean on an empty label (CLI `n8n execute`; schedule triggers cannot be CLI-started, hence the manual trigger node).
- NOT yet verified: replay (run twice, one row), forced-failure path, HubSpot contact poll (needs the HubSpot token), intake overlap if a run exceeds 1 min (fine in Phase 1; Phase 2 needs a claim row).
- Known gap: the error alert cannot name the lead's source id (the Error Trigger does not carry it). Phase 2 fix: process each message in its own sub-workflow with an error output.
- Concession: Gmail OAuth grants send scope, so "the workflow holds no send permission" is true by design (only the alert email sends), not by credential scope.

Open before Phase 2:
- Which Claude model for extract and for draft.
- Confirm eval thresholds (40 fixtures, 90% fields, 95% lead detection).
