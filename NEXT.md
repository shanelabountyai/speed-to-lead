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

Next: build the spine as sub-workflows (error handler, run-log writer), then the Gmail + HubSpot poll triggers with dedupe on the source id. Needs credentials from Shane first: Gmail OAuth, Google Sheets OAuth (run-log sheet), HubSpot token.

Open before Phase 2:
- Which Claude model for extract and for draft.
- Confirm eval thresholds (40 fixtures, 90% fields, 95% lead detection).
