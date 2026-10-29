"""Writes workflows/dev-eval-run.json: every fixture, in order, through process-lead (no live inbox needed).
Usage: python3 scripts/gen_eval_run.py [n1-fixtures|holdout]. scripts/eval.sh runs this, imports, executes and scores both sets."""
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else "n1-fixtures"   # or "holdout"
fx = json.load(open(root / f"fixtures/{name}.json"))["fixtures"]
items = [{"json": {"source": "fixture", "source_id": f["id"], "from_email": f["from_email"], "subject": f["subject"], "body": f["body"]}} for f in fx]
w = {"id": "n1DevEvalRun0001" if name == "n1-fixtures" else "n1DevEvalHold001", "name": f"Dev: run {name} through process lead", "nodes": [
  {"parameters": {}, "name": "Run once", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0]},
  {"parameters": {"jsCode": "return " + json.dumps(items) + ";"}, "name": "Fixtures", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0]},
  {"parameters": {"source": "database", "workflowId": {"__rl": True, "value": "n1ProcessLead0001", "mode": "id"}, "options": {}}, "name": "Process lead", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2, "position": [440, 0]}],
  "connections": {"Run once": {"main": [[{"node": "Fixtures", "type": "main", "index": 0}]]}, "Fixtures": {"main": [[{"node": "Process lead", "type": "main", "index": 0}]]}},
  "active": False, "settings": {"executionOrder": "v1"}, "pinData": {}}
json.dump(w, open(root / ("workflows/dev-eval-run.json" if name == "n1-fixtures" else f"workflows/dev-eval-{name}.json"), "w"), indent=2)
