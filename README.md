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
