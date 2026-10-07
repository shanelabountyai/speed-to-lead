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

Wired 2026-10-05 (ids, no secrets): run-log sheet `Speed-to-Lead Run Log`, id `1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY` (tabs `runs`, `review`). n8n data is in `~/.n8n-speed-to-lead/.n8n/`. Credentials: Gmail `GGGxY4DRdE9giH2x`, Sheets `McOy4auCNkFX0Os2`; HubSpot `u1WBi64R7zas6Zfn`. n8n's Gmail account is shanelabountyai@gmail.com (label `n1-lead` made by hand there, 1,165-message inbox). The Gmail connector Claude sees is a DIFFERENT mailbox (10.8k messages), where Claude created a stray `n1-lead` label (Label_2): delete it.

Built 2026-10-05 (in `workflows/`, import with `ALERT_TO=<addr> scripts/import.sh` while n8n is stopped; the script substitutes the alert address so it never lands in git):
- `run-log-writer` (sub-workflow, appends to `runs`), `error-handler` (alert email, throttled to one per 15 min, then logs), `intake-phase1` (schedule 1 min, Gmail search `label:n1-lead` (by name, NOT a label id: ids differ per account), reads `runs`, skips messages already logged non-error, stub where Phase 2 goes, writes `spine_ok`), `init-headers` (run once; already run, headers verified).
- Design choice: intake uses Schedule + Gmail getAll and dedupes against the sheet, not the Gmail Trigger. The trigger advances its cursor even when a run fails, so a failed lead would never be re-polled. This way anything not logged is picked up again, including mail that arrived while n8n was off.
- `intake-hubspot-phase1` (added): every minute, searches HubSpot contacts created in the last 24h, same dedupe and log as the Gmail intake, source ids prefixed `hubspot:`. Credential `HubSpot Service Key account` (`u1WBi64R7zas6Zfn`). Verified: token works (CLI run succeeded; account has no contacts yet, so no rows).
- Verified 2026-10-07: Gmail replay. One labelled test email gives exactly one `runs` row; second poll picks nothing. Run-log write is an upsert on `source_id` (`appendOrUpdate`): the first version appended with retry-on-fail and wrote the same row 3 times (retries re-sent a write that had landed), so a write must be idempotent, not just retried. Sub-workflows must be PUBLISHED (`n8n publish:workflow --id=...`) before another workflow can call them; the CLI says so with 'Workflow is not active'.
- Dev tooling: `workflows/dev-reset-log.json` clears `runs`/`review` rows (keeps headers) between tests. CLI runs need n8n stopped (port 5679 clash).
- Verified: headers in both tabs, intake runs clean on an empty label (CLI `n8n execute`; schedule triggers cannot be CLI-started, hence the manual trigger node).
- NOT yet verified: forced-failure path, HubSpot poll against a real new contact, intake overlap if a run exceeds 1 min (fine in Phase 1; Phase 2 needs a claim row).
- Known gap: the error alert cannot name the lead's source id (the Error Trigger does not carry it). Phase 2 fix: process each message in its own sub-workflow with an error output.
- Concession: Gmail OAuth grants send scope, so "the workflow holds no send permission" is true by design (only the alert email sends), not by credential scope.

Open before Phase 2:
- Which Claude model for extract and for draft.
- Confirm eval thresholds (40 fixtures, 90% fields, 95% lead detection).

Security note: `hs auth` writes `hubspot.config.yml` (a personal access key) into the project folder. It is gitignored and was removed from history before any push; the key was shown in a session transcript, so rotate it.
