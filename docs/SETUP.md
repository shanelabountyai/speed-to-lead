# Setup: fresh n8n to a working run

For a builder installing N1 on a new machine. About 45 minutes, most of it Google's consent screens. Everything here is demo-safe: demo mode is on, only `example.com` addresses get drafts, and no step sends mail.

You need three accounts: **Google** (one OAuth app covers Gmail and Sheets), **HubSpot** (a service key), **Anthropic** (an API key). Never paste a key into a file in this repo; credentials live only in n8n's store.

## 1. Run n8n

n8n 2.27.5 needs Node 22 (it fails on Node 26: `isolated-vm` will not build).

```bash
mkdir ~/.n8n-runtime && cd ~/.n8n-runtime && npm i node@22 n8n@2.27.5
PATH=$HOME/.n8n-runtime/node_modules/.bin:$PATH N8N_USER_FOLDER=$HOME/.n8n-speed-to-lead n8n start
```

Editor: http://localhost:5678. Create the owner account on first load. Then stop n8n (Ctrl-C): imports and CLI runs need port 5679 free.

## 2. Create the credentials (in the editor, then stop n8n again)

| Name (exact) | Type | Notes |
|---|---|---|
| `Gmail account` | Gmail OAuth2 | the mailbox that receives leads and holds drafts |
| `Google Sheets account` | Google Sheets OAuth2 | same Google OAuth client as Gmail |
| `HubSpot Service Key account` | HubSpot App Token | service key scopes: contacts read/write, tasks read/write, crm.schemas.contacts write |
| `Anthropic account` | Anthropic API | |

Google OAuth in Testing mode lapses every 7 days and n8n's UI still says "connected". If a Gmail or Sheets node fails with "reconnect", reconnect it; publish the Google app to production to stop this.

## 3. Create the run-log sheet and point the workflows at your ids

1. In Google Sheets create a spreadsheet; name it `Speed-to-Lead Run Log`; add tabs `runs` and `review`. Copy its id from the URL.
2. The workflow JSON carries the ids of the original install. Each credential's id is in the editor URL when you open it. Replace the old ids with yours:

```bash
sed -i '' \
  -e 's/1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY/<your sheet id>/g' \
  -e 's/GGGxY4DRdE9giH2x/<gmail credential id>/g' \
  -e 's/McOy4auCNkFX0Os2/<sheets credential id>/g' \
  -e 's/u1WBi64R7zas6Zfn/<hubspot credential id>/g' \
  -e 's/iX5UtPD5bryOqgFt/<anthropic credential id>/g' \
  workflows/*.json scripts/*.py
```

   Do not commit this change (these ids are the repo's reference install). Use a branch or `git stash` afterwards.
3. In Gmail, create the label `n1-lead` (by name; label ids differ per account).

## 4. Import and publish

```bash
ALERT_TO=you@yourdomain.com scripts/import.sh
```

It imports every workflow and publishes `run-log-writer`, `error-handler` and `process-lead`. The error workflow must be published or nothing alerts. Re-importing un-publishes, so re-run the script, not a bare import.

## 5. Prepare the sheet and HubSpot (each is a one-shot workflow, safe to run twice)

```bash
export PATH=$HOME/.n8n-runtime/node_modules/.bin:$PATH N8N_USER_FOLDER=$HOME/.n8n-speed-to-lead
n8n execute --id=n1DevRuleTabs0001     # rule tabs (score_rules, bands, routing, rates, config) and the 19-column run-log header
n8n execute --id=n1DevSeedHubspot1     # custom contact properties (demo_record, lead_score, ...) and 8 example.com contacts
```

Then set your HubSpot owner id: it is `hubspot_owner_id` in `rules/config.json` and in the sheet's `config` tab (HubSpot, Settings, Users; or `GET /crm/v3/owners`).

## 6. Prove it works

```bash
scripts/eval.sh      # n8n stopped; exits 0 and prints "EVAL GATE: PASS"
```

It runs the unit tests, then 40 tuned and 15 held-out messages through `process-lead` with no live inbox, and scores them. Expect fields at 90% or better, zero invented values, lead detection 95% or better, rules 100%, no injection obeyed. It creates demo contacts, example.com drafts and tasks, and tears down the previous run's first. Cost is about $0.07 for both sets ($0.0013 per message).

## 7. Go live (production mode)

Publish the schedules: `intake-phase1` (`n1IntakePhase01`, Gmail, every minute), `intake-hubspot-phase1` (`n1HubspotPhase01`, HubSpot, every minute) and `approval-check` (`n1ApprovalCheck01`, every 30 minutes) with `n8n publish:workflow --id=<id>`, then start n8n. Label an email `n1-lead`; within a few minutes there is a contact, a task and a draft in the thread. Demo mode (`demo_mode` in config) stays `true` until you are working on real contacts.

## When it goes wrong

| Symptom | Cause and fix |
|---|---|
| `NODE_MODULE_VERSION` / `isolated-vm` build error | Wrong Node. Use the Node 22 in `~/.n8n-runtime`. |
| CLI run says port in use | n8n is still running. Stop it. |
| Node says "reconnect" or 401 from Google | The 7-day Testing-mode expiry. Reconnect the credential. |
| Sub-workflow "Workflow is not active" | It is not published. Re-run `scripts/import.sh`. |
| Sweep fails in about 5 s per message with nothing rendered | Rule tabs or the HubSpot seed are missing: redo step 5. |
| Every poll re-fails after a bad batch | Two messages from one sender in a batch used to do this; fixed in `upsertInputs`. Check the run log for the error text first. |
| Gmail 429 on teardown | Too many parallel draft calls; teardown already batches 5/s. Run it again. |
| Drafts marked `discarded` after a log reset | `approval-check` saw rows whose drafts were deleted. Reset the log (`n1ResetLog00001`) before the next run. |
| Alert flood | There is none by design: one alert per 15 minutes; every failure is still logged. |
