# Speed-to-Lead (N1)

First workflow in the n8n Automation track. A new lead becomes a scored, routed HubSpot record with a drafted reply waiting for approval. Also defines the spine N2 to N10 reuse.

- PRD: https://claude.ai/artifact/FAz82XgxDT9xWHw2DG6F75
- Build log: https://claude.ai/artifact/28KeGV3xfBwcBuoMEQjFMj
- Demo firm: Tallgrass Advisory (fictional). Demo data only; nothing here runs on real contacts.
- Stack: n8n (self-hosted), HubSpot, Gmail, Claude. QuickBooks is out of scope.

## Layout

- `fixtures/n1-fixtures.json`: 40 labeled messages with expected results (the eval set)
- `fixtures/README.md`: fields and how to score a run
- `fixtures/build.py`: regenerates the JSON; expected results compute from the PRD's rule tables
- `workflows/`: n8n exports, imported with `scripts/import.sh` (see `NEXT.md`)
- `tests/`: offline checks, no dependencies and no n8n or credentials needed. Run `npm test` (or `node --test`) with Node 22+ and `python3` on PATH. They lint the workflow exports (wiring, sub-workflow and error-workflow references, the no-retry-on-writes rule, the run-log columns, no committed secrets or addresses), execute the Code nodes' dedupe and alert-throttle logic against mocked inputs, pin the fixtures to the claims in `fixtures/README.md`, and check that `build.py` regenerates `n1-fixtures.json` exactly.
