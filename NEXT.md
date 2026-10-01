# Next

Status: PRD drafted and fixtures written (2026-10-01). No workflow built yet.

1. Phase 1, the spine: triggers (polling), idempotency, error path, run log. No model calls.
2. Phase 2: extraction, scoring, routing, HubSpot write, cost per run.
3. Phase 3: draft reply and approval.
4. Phase 4: eval gate, setup doc, capstone demo.

Decided 2026-10-01: a real lead carrying an injected instruction gets a contact (scored and routed from what it honestly states), no draft, and a review row.

Open before Phase 1:
- n8n version, and whether it has an Anthropic node or model calls go through an HTTP request.

Open before Phase 2:
- Which Claude model for extract and for draft.
- Confirm eval thresholds (40 fixtures, 90% fields, 95% lead detection).
