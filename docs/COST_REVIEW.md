# Cost review at closure (2026-11-02)

Local-only project: no Vercel, no Neon, no cron service, no GitHub Actions (`.github/` does not exist). Nothing bills while n8n is stopped (checked: nothing listening on :5678).

| Item | What can bill | Decision | Restore note |
|---|---|---|---|
| 3 n8n schedules (`intake-phase1` 1 min, `intake-hubspot-phase1` 1 min, `approval-check` 30 min) | Only fire while n8n runs; each poll is a Gmail/HubSpot/Sheets read, no model call unless a new lead is found | **Keep, but n8n stays stopped.** Start n8n only for a demo or eval | `ALERT_TO=<addr> scripts/import.sh` un-publishes everything; republish the three with the loop in DEMO.md |
| Anthropic API (Haiku 4.5 extraction + ack, `lib/draft.js`) | $0.0013 per message incl. drafts; $0.049 per 40-lead run. One eval (55 messages) is about $0.07 | **Keep.** Spend only happens on a new lead or an eval run | Key lives in the n8n credential; revoke it in the Anthropic console if the project is retired |
| HubSpot (developer/free portal) | Free tier; demo contacts and tasks are `example.com` and removed by teardown | **Keep** | Run `dev-teardown-hubspot` after any demo |
| Gmail / Google Sheets APIs | Free quota; Gmail 429s at about 20 parallel draft deletes (already throttled to 5/s) | **Keep** | none |
| Google OAuth in Testing mode | No cost; tokens lapse every 7 days | **Keep**; reconnect before a demo | Publish the OAuth app to stop the weekly lapse |
| Always-on hosting / database | None exists | **n/a** | none |

Baseline for later checks: $0.0013 per message, $0.049 per 40 leads, 0 listeners on :5678 at closure.
Anthropic usage by key is the one meter to look at if a bill ever appears: Console, Usage, filter by this key.
