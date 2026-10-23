"""Generates the dev setup workflows (run once, safe to run twice): HubSpot properties + synthetic contacts, teardown, and the rule tabs in the run-log sheet.
Usage: python3 scripts/gen_dev.py   (writes workflows/dev-*.json)"""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
SHEET = "1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY"
GS = {"googleSheetsOAuth2Api": {"id": "McOy4auCNkFX0Os2", "name": "Google Sheets account"}}
HS = {"hubspotAppToken": {"id": "u1WBi64R7zas6Zfn", "name": "HubSpot Service Key account"}}
fx = json.load(open(root / "fixtures/n1-fixtures.json"))["fixtures"]
rd = lambda n: json.load(open(root / f"rules/{n}.json"))

def node(name, type, tv, pos, params, **kw): return {"parameters": params, "name": name, "type": type, "typeVersion": tv, "position": pos, **kw}
def http(name, pos, method, url, body, cred, kind, never_error=False):
    p = {"method": method, "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": kind}
    if body is not None: p.update(sendBody=True, specifyBody="json", jsonBody=body)
    if never_error: p["options"] = {"response": {"response": {"neverError": True}}}
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, credentials=cred)
def chain(names): return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}
def wf(id, name, nodes): return {"id": id, "name": name, "nodes": nodes, "connections": chain([n["name"] for n in nodes]), "active": False, "settings": {"executionOrder": "v1"}, "pinData": {}}
def js(x): return json.dumps(x)
manual = lambda: node("Run once", "n8n-nodes-base.manualTrigger", 1, [0, 0], {})

# ---- HubSpot: custom properties, then synthetic contacts (fake people, example.com emails, never real)
props = [("demo_record", "Demo record", "bool", "booleancheckbox"), ("demo_owner", "Demo owner", "string", "text"), ("lead_score", "Lead score", "number", "number"),
         ("lead_band", "Lead band", "string", "text"), ("lead_segment", "Lead segment", "string", "text"), ("lead_score_reasons", "Lead score reasons", "string", "textarea")]
prop_nodes = [http(f"Property {n}", [220 + 220 * i, 0], "POST", "https://api.hubapi.com/crm/v3/properties/contacts",
                   js({"name": n, "label": l, "type": t, "fieldType": ft, "groupName": "contactinformation", **({"options": [{"label": "Yes", "value": "true", "displayOrder": 0}, {"label": "No", "value": "false", "displayOrder": 1}]} if t == "bool" else {})}), HS, "hubspotAppToken", True) for i, (n, l, t, ft) in enumerate(props)]
SEED = ["F01", "F02", "F03", "F04", "F05", "F06", "F21", "F22"]
leads = [f for f in fx if f["id"] in SEED] if all(any(f["id"] == s for f in fx) for s in SEED) else [f for f in fx if f["labels"]["is_lead"]][:8]
def contact(f):
    first, last = f["from_name"].split(" ", 1)
    return {"id": f["from_name"].lower().replace(" ", ".") + "@example.com", "idProperty": "email",
            "properties": {"email": f["from_name"].lower().replace(" ", ".") + "@example.com", "firstname": first, "lastname": last, "company": f["labels"]["company"] or "", "message": f["body"], "demo_record": "true"}}
seed = http("Upsert synthetic contacts", [220 + 220 * len(props), 0], "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert", js({"inputs": [contact(f) for f in leads]}), HS, "hubspotAppToken")
json.dump(wf("n1DevSeedHubspot1", "Dev: seed HubSpot properties and synthetic contacts", [manual()] + prop_nodes + [seed]), open(root / "workflows/dev-seed-hubspot.json", "w"), indent=2)

# ---- HubSpot teardown: archive every demo_record contact
search = http("Find demo contacts", [220, 0], "POST", "https://api.hubapi.com/crm/v3/objects/contacts/search",
              js({"filterGroups": [{"filters": [{"propertyName": "demo_record", "operator": "EQ", "value": "true"}]}], "limit": 100}), HS, "hubspotAppToken")
shape = node("Shape archive batch", "n8n-nodes-base.code", 2, [440, 0], {"jsCode": "return [{ json: { inputs: ($json.results ?? []).map(c => ({ id: c.id })) } }];"})
arch = http("Archive demo contacts", [660, 0], "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/archive", "={{ JSON.stringify($json) }}", HS, "hubspotAppToken")
json.dump(wf("n1DevTeardownHs01", "Dev: teardown (archive every demo_record contact)", [manual(), search, shape, arch]), open(root / "workflows/dev-teardown-hubspot.json", "w"), indent=2)

# ---- Sheet: rule tabs and the wider run-log header
RUNS = ["time", "source", "source_id", "outcome", "time_to_draft_s", "cost_usd", "error", "score", "band", "segment", "demo_owner", "input_tokens", "output_tokens", "draft_id", "thread_id", "draft_check", "task_id", "approval", "approval_at"]
tabs = {"score_rules": rd("score_rules"), "bands": rd("bands"), "routing": rd("routing"), "rates": rd("rates"), "config": rd("config")}
base = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}"
nodes = [manual(), http("Add tabs", [220, 0], "POST", f"{base}:batchUpdate", js({"requests": [{"addSheet": {"properties": {"title": t}}} for t in tabs]}), GS, "googleSheetsOAuth2Api", True)]
def put(name, pos, tab, rows):
    return http(name, pos, "PUT", f"{base}/values/{tab}!A1?valueInputOption=RAW", js({"values": rows}), GS, "googleSheetsOAuth2Api")
nodes.append(put("Runs header", [440, 0], "runs", [RUNS]))
for i, (t, rows) in enumerate(tabs.items()):
    cols = list(rows[0].keys())
    nodes.append(put(f"Tab {t}", [660 + 220 * i, 0], t, [cols] + [[r[c] for c in cols] for r in rows]))
json.dump(wf("n1DevRuleTabs0001", "Dev: write rule tabs and wider run-log header", nodes), open(root / "workflows/dev-rule-tabs.json", "w"), indent=2)
print("seed contacts:", [f["id"] for f in leads])
