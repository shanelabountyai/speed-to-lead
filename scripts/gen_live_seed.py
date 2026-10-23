"""Writes workflows/dev-live-seed.json: sends two test emails to the owner's own mailbox (address filled in by scripts/import.sh),
labels them n1-lead, and creates one synthetic HubSpot contact, so the live intakes have something to pick up. Safe to rerun (new messages each time)."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
ho = {f["id"]: f for f in json.load(open(root / "fixtures/holdout.json"))["fixtures"]}
GM = {"gmailOAuth2": {"id": "GGGxY4DRdE9giH2x", "name": "Gmail account"}}
HS = {"hubspotAppToken": {"id": "u1WBi64R7zas6Zfn", "name": "HubSpot Service Key account"}}
LABEL = "Label_6272275298497821958"  # n1-lead in shanelabountyai@gmail.com; label ids differ per account
nodes = [{"parameters": {}, "name": "Run once", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0]}]
conns = {"Run once": {"main": [[]]}}
for i, hid in enumerate(["H01", "H09"]):
    f = ho[hid]; y = i * 160
    nodes.append({"parameters": {"resource": "message", "operation": "send", "sendTo": "__ALERT_TO__", "subject": "Live test: " + f["subject"], "emailType": "text",
        "message": f"Demo-From: {f['from_email']}\n" + f["body"], "options": {"appendAttribution": False}}, "name": f"Send {hid}", "type": "n8n-nodes-base.gmail", "typeVersion": 2.2, "position": [220, y], "credentials": GM, "retryOnFail": False})
    nodes.append({"parameters": {"resource": "message", "operation": "addLabels", "messageId": "={{ $json.id }}", "labelIds": [LABEL]}, "name": f"Label {hid}", "type": "n8n-nodes-base.gmail", "typeVersion": 2.2, "position": [440, y], "credentials": GM, "retryOnFail": False})
    conns["Run once"]["main"][0].append({"node": f"Send {hid}", "type": "main", "index": 0})
    conns[f"Send {hid}"] = {"main": [[{"node": f"Label {hid}", "type": "main", "index": 0}]]}
f = ho["H05"]
body = {"inputs": [{"id": "pete.dalton@example.com", "idProperty": "email", "properties": {"email": "pete.dalton@example.com", "firstname": "Pete", "lastname": "Dalton", "company": "Dalton Roofing", "message": f["body"], "demo_record": "true"}}]}
nodes.append({"parameters": {"method": "POST", "url": "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert", "authentication": "predefinedCredentialType", "nodeCredentialType": "hubspotAppToken", "sendBody": True, "specifyBody": "json", "jsonBody": json.dumps(body)},
              "name": "Create HubSpot contact", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [220, 320], "credentials": HS})
conns["Run once"]["main"][0].append({"node": "Create HubSpot contact", "type": "main", "index": 0})
json.dump({"id": "n1DevLiveSeed0001", "name": "Dev: send 2 labelled test emails and create 1 HubSpot contact", "nodes": nodes, "connections": conns, "active": False, "settings": {"executionOrder": "v1"}, "pinData": {}}, open(root / "workflows/dev-live-seed.json", "w"), indent=2)
