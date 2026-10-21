"""Generates the Phase 2 workflows: process-lead (new), and rewires the two intakes and the run-log writer.
The logic lives in lib/*.js (unit-tested); this embeds it into n8n Code nodes so tests and workflow cannot drift.
Usage: python3 scripts/build_phase2.py"""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
SHEET = "1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY"
GS = {"googleSheetsOAuth2Api": {"id": "McOy4auCNkFX0Os2", "name": "Google Sheets account"}}
AN = {"anthropicApi": {"id": "iX5UtPD5bryOqgFt", "name": "Anthropic account"}}
HS = {"hubspotAppToken": {"id": "u1WBi64R7zas6Zfn", "name": "HubSpot Service Key account"}}
READ_RETRY = dict(retryOnFail=True, maxTries=3, waitBetweenTries=2000)
PROCESS_ID, WRITER_ID = "n1ProcessLead0001", "n1RunLogWriter01"

def bundle():
    """scoring.js + lead.js as one prelude defining `L` (lead.js exports) for a Code node."""
    out = "const __lib = {}; const require = (p) => __lib[p];\n"
    for n in ("scoring", "lead"):
        out += f"__lib['./{n}'] = (() => {{ const module = {{ exports: {{}} }};\n{(root / 'lib' / (n + '.js')).read_text()}\nreturn module.exports; }})();\n"
    return out + "const L = __lib['./lead'];\n"
PRELUDE = bundle()
def code(name, pos, body, each=False, once=False):
    p = {"jsCode": PRELUDE + body}
    if each: p["mode"] = "runOnceForEachItem"
    n = {"parameters": p, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}
    # executeOnce would feed an all-items Code node only its FIRST input item; the mode already runs once per batch.
    return n
def node(name, type, tv, pos, params, **kw): return {"parameters": params, "name": name, "type": type, "typeVersion": tv, "position": pos, **kw}
def link(c, a, b, out=0):
    c.setdefault(a, {"main": []})
    while len(c[a]["main"]) <= out: c[a]["main"].append([])
    c[a]["main"][out].append({"node": b, "type": "main", "index": 0})
def link_in(c, a, b, idx):  # connect a -> b's input number idx
    c.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": idx})
def wf(id, name, nodes, conns, settings=None):
    return {"id": id, "name": name, "nodes": nodes, "connections": conns, "active": False, "settings": {"executionOrder": "v1", **(settings or {})}, "pinData": {}}
def cond_bool(left, want=True, cid="c1"):
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{"id": cid, "leftValue": left, "rightValue": "", "operator": {"type": "boolean", "operation": "true" if want else "false", "singleValue": True}}], "combinator": "and"}, "options": {}}
def sheets_upsert(name, pos, tab, cols, match, **kw):
    return node(name, "n8n-nodes-base.googleSheets", 4.7, pos, {"operation": "appendOrUpdate", "documentId": {"__rl": True, "value": SHEET, "mode": "id"}, "sheetName": {"__rl": True, "value": tab, "mode": "name"},
        "columns": {"mappingMode": "defineBelow", "value": {c: ("={{ $now.toISO() }}" if c == "time" else f"={{{{ $json.{c} }}}}") for c in cols}, "matchingColumns": [match],
                    "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True} for c in cols]}, "options": {}},
        credentials=GS, retryOnFail=False, **kw)
RUNS = ["time", "source", "source_id", "outcome", "time_to_draft_s", "cost_usd", "error", "score", "band", "segment", "demo_owner", "input_tokens", "output_tokens"]
REVIEW = ["time", "source", "source_id", "from", "subject", "reason", "raw_output"]

# ---------------- run-log writer: wider columns
w = json.load(open(root / "workflows/run-log-writer.json"))
for n in w["nodes"]:
    if n["name"] == "Upsert run":
        n["parameters"]["columns"]["value"] = {c: ("={{ $now.toISO() }}" if c == "time" else f"={{{{ $json.{c} ?? '' }}}}") for c in RUNS}
        n["parameters"]["columns"]["schema"] = [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True} for c in RUNS]
json.dump(w, open(root / "workflows/run-log-writer.json", "w"), indent=2)

# ---------------- process-lead
N = {}
nodes = [node("When called", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [0, 0], {"inputSource": "passthrough"})]
rng = "&".join(f"ranges={t}" for t in ("config", "score_rules", "bands", "routing", "rates", "runs"))
nodes.append(node("Load tables", "n8n-nodes-base.httpRequest", 4.2, [220, 0], {"method": "GET", "url": f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}/values:batchGet?{rng}", "authentication": "predefinedCredentialType", "nodeCredentialType": "googleSheetsOAuth2Api"}, credentials=GS, executeOnce=True, **READ_RETRY))
nodes.append(code("Prep", [440, 0], """
const T = L.tablesFromRanges($('Load tables').first().json.valueRanges);
const cfg = Object.fromEntries(T.config.map((r) => [r.key, r.value]));
const spent = L.todayCost(T.runs, $now.toISO().slice(0, 10));
if (spent >= Number(cfg.daily_cap_usd)) throw new Error(`Daily cost cap reached: $${spent.toFixed(4)} of $${cfg.daily_cap_usd}. Model steps stopped; leads stay queued for the next poll.`);
return $('When called').all().map((it, idx) => {
  const msg = it.json;
  const allowed = !(cfg.demo_mode === 'true' && !L.demoAllowed(msg.from_email));
  return { json: { idx, msg, allowed, request: allowed ? L.buildRequest(msg, cfg.extract_model) : null } };
});""", once=True))
nodes.append(node("Allowed?", "n8n-nodes-base.if", 2.2, [660, 0], cond_bool("={{ $json.allowed }}")))
nodes.append(node("Extract", "n8n-nodes-base.httpRequest", 4.2, [880, -120], {"method": "POST", "url": "https://api.anthropic.com/v1/messages", "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]}, "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}"},
    credentials=AN, retryOnFail=True, maxTries=2, waitBetweenTries=3000))
validate = """
const prev = $('%s').item.json;
const text = $json.content?.[0]?.text ?? '';
const u = $json.usage ?? {};
const usage = { input_tokens: (prev.usage?.input_tokens ?? 0) + (u.input_tokens ?? 0), output_tokens: (prev.usage?.output_tokens ?? 0) + (u.output_tokens ?? 0) };
const r = L.parseExtraction(text);
return { json: { idx: prev.idx, msg: prev.msg, request: prev.request, usage, ok: r.ok, ex: r.ok ? r.data : null, reason: r.ok ? '' : r.reason, raw: r.ok ? '' : text.slice(0, 500) } };"""
nodes.append(code("Validate", [1100, -120], validate % "Prep", each=True))
nodes.append(node("Valid?", "n8n-nodes-base.if", 2.2, [1320, -120], cond_bool("={{ $json.ok }}")))
nodes.append(node("Retry extract", "n8n-nodes-base.httpRequest", 4.2, [1540, 0], {"method": "POST", "url": "https://api.anthropic.com/v1/messages", "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]}, "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}"},
    credentials=AN, retryOnFail=True, maxTries=2, waitBetweenTries=3000))
nodes.append(code("Validate retry", [1760, 0], validate % "Validate", each=True))
nodes.append(code("Mark skipped", [880, 160], "const p = $json; return { json: { idx: p.idx, msg: p.msg, ok: true, ex: null, usage: { input_tokens: 0, output_tokens: 0 }, skipped: true } };", each=True))
nodes.append(node("Gather", "n8n-nodes-base.merge", 3, [1980, 0], {"numberInputs": 3}))
nodes.append(code("Decide", [2200, 0], """
const T = L.tablesFromRanges($('Load tables').first().json.valueRanges);
const cfg = Object.fromEntries(T.config.map((r) => [r.key, r.value]));
const items = $input.all().map((i) => i.json).sort((a, b) => a.idx - b.idx);
const decided = L.decideBatch(items.map((i) => ({ msg: i.msg, ex: i.skipped ? undefined : i.ex })), T, T.runs);
return decided.map((d, k) => {
  const it = items[k];
  const cost = it.skipped ? 0 : L.costUsd(it.usage, T.rates, cfg.extract_model);
  return { json: { ...d, raw: it.raw ?? '', cost_usd: Number(cost.toFixed(6)), input_tokens: it.usage.input_tokens, output_tokens: it.usage.output_tokens } };
});""", once=True))
nodes.append(code("Build upsert", [2420, 0], "return [{ json: { inputs: $input.all().map((i) => i.json).filter((d) => d.contact).map(L.contactInput) } }];", once=True))
nodes.append(node("Any contacts?", "n8n-nodes-base.if", 2.2, [2640, 0], {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
    "conditions": [{"id": "c2", "leftValue": "={{ $json.inputs.length }}", "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}], "combinator": "and"}, "options": {}}))
nodes.append(node("Upsert contacts", "n8n-nodes-base.httpRequest", 4.2, [2860, -80], {"method": "POST", "url": "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert", "authentication": "predefinedCredentialType", "nodeCredentialType": "hubspotAppToken",
    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json) }}"}, credentials=HS, retryOnFail=False))
nodes.append(code("Verify upsert", [3080, -80], """
// A batch can come back partly failed. Throw so nothing is logged and the next poll retries; the upsert is idempotent on email.
const want = $('Build upsert').first().json.inputs.length;
const r = $json;
if (r.status !== 'COMPLETE' || (r.errors && r.errors.length) || (r.results ?? []).length !== want) throw new Error(`HubSpot upsert incomplete: ${r.status}, ${(r.results ?? []).length}/${want} records, ${JSON.stringify(r.errors ?? []).slice(0, 300)}`);
return [{ json: { ok: true } }];""", once=True))
nodes.append(node("Contacts done", "n8n-nodes-base.noOp", 1, [3300, 0], {}))
nodes.append(code("Review rows", [3520, -100], """
return $('Decide').all().map((i) => i.json).filter((d) => d.review).map((d) => ({ json: { source: d.source, source_id: d.source_id, from: d.from_email, subject: d.subject, reason: d.review_reason, raw_output: d.raw || '' } }));""", once=True))
nodes.append(sheets_upsert("Write review", [3740, -100], "review", REVIEW, "source_id"))
nodes.append(code("Log rows", [3520, 120], """
return $('Decide').all().map((i) => i.json).map((d) => ({ json: { source: d.source, source_id: d.source_id, outcome: d.outcome, time_to_draft_s: '', cost_usd: d.cost_usd, error: '', score: d.score ?? '', band: d.band ?? '', segment: d.segment ?? '', demo_owner: d.demo_owner ?? '', input_tokens: d.input_tokens, output_tokens: d.output_tokens } }));""", once=True))
nodes.append(node("Write run log", "n8n-nodes-base.executeWorkflow", 1.2, [3740, 120], {"source": "database", "workflowId": {"__rl": True, "value": WRITER_ID, "mode": "id"}, "options": {}}))
c = {}
for a, b in [("When called", "Load tables"), ("Load tables", "Prep"), ("Prep", "Allowed?")]: link(c, a, b)
link(c, "Allowed?", "Extract", 0); link(c, "Allowed?", "Mark skipped", 1)
link(c, "Extract", "Validate"); link(c, "Validate", "Valid?")
link_in(c, "Valid?", "Gather", 0)  # true branch (output 0)
link(c, "Valid?", "Retry extract", 1)
link(c, "Retry extract", "Validate retry"); link_in(c, "Validate retry", "Gather", 1); link_in(c, "Mark skipped", "Gather", 2)
# Valid? output 0 must go to Gather: link_in wrote it into main[0] already, then Retry extract is main[1]
c["Valid?"] = {"main": [[{"node": "Gather", "type": "main", "index": 0}], [{"node": "Retry extract", "type": "main", "index": 0}]]}
for a, b in [("Gather", "Decide"), ("Decide", "Build upsert"), ("Build upsert", "Any contacts?")]: link(c, a, b)
link(c, "Any contacts?", "Upsert contacts", 0); link(c, "Any contacts?", "Contacts done", 1)
link(c, "Upsert contacts", "Verify upsert"); link(c, "Verify upsert", "Contacts done")
link(c, "Contacts done", "Review rows"); link(c, "Contacts done", "Log rows")
link(c, "Review rows", "Write review"); link(c, "Log rows", "Write run log")
json.dump(wf(PROCESS_ID, "N1 process lead (phase 2)", nodes, c, {"errorWorkflow": "n1ErrorHandler01"}), open(root / "workflows/process-lead.json", "w"), indent=2)

# ---------------- intakes call process-lead instead of the stub
def rewire(path, pick_js, extra=None):
    w = json.load(open(root / path))
    by = {n["name"]: n for n in w["nodes"]}
    keep = [n for n in w["nodes"] if n["name"] not in ("Phase 2 stub: extract, score, route, draft", "Shape log row", "Write run log", "Process lead")]
    by["Pick unseen"]["parameters"]["jsCode"] = pick_js
    keep.append(node("Process lead", "n8n-nodes-base.executeWorkflow", 1.2, [880, 0], {"source": "database", "workflowId": {"__rl": True, "value": PROCESS_ID, "mode": "id"}, "options": {}}))
    w["nodes"] = keep
    w["connections"]["Pick unseen"] = {"main": [[{"node": "Process lead", "type": "main", "index": 0}]]}
    for k in ("Phase 2 stub: extract, score, route, draft", "Shape log row"): w["connections"].pop(k, None)
    json.dump(w, open(root / path, "w"), indent=2)
rewire("workflows/intake-phase1.json", """// Seen = any log row for this message with a non-error outcome. Replay-safe: re-running changes nothing.
const rows = $('Read run log').all().map(i => i.json).filter(r => r.source_id);
const done = new Set(rows.filter(r => r.outcome !== 'error').map(r => r.source_id));
return $('List labelled mail').all()
  .filter(i => !done.has(i.json.id))
  .map(i => {
    const text = String(i.json.text ?? i.json.snippet ?? '');
    // Demo mode: the seed script puts the fixture's sender on a 'Demo-From:' first line, so a test message sent from a real mailbox carries a synthetic sender.
    const demo = text.match(/^\\s*Demo-From:\\s*(\\S+)/i);
    return { json: {
      source: 'gmail',
      source_id: i.json.id,
      from_email: demo ? demo[1] : (i.json.from?.value?.[0]?.address ?? ''),
      subject: i.json.subject ?? '',
      body: demo ? text.replace(/^\\s*Demo-From:.*\\n?/i, '') : text,
    }};
  });""")
rewire("workflows/intake-hubspot-phase1.json", """// ponytail: looks back 24h and dedupes against the run log, so a missed poll or a failed run is retried. Longer outages need a wider window.
const rows = $('Read run log').all().map(i => i.json).filter(r => r.source_id);
const done = new Set(rows.filter(r => r.outcome !== 'error').map(r => r.source_id));
return ($('Search new contacts').first().json.results ?? [])
  .filter(c => !done.has('hubspot:' + c.id))
  .map(c => ({ json: { source: 'hubspot', source_id: 'hubspot:' + c.id, from_email: c.properties?.email ?? '',
    subject: 'HubSpot form', body: [c.properties?.firstname, c.properties?.lastname].filter(Boolean).join(' ') + '\\n' + (c.properties?.company ?? '') + '\\n\\n' + (c.properties?.message ?? '') } }));""")
# the HubSpot search must also return the form message
w = json.load(open(root / "workflows/intake-hubspot-phase1.json"))
for n in w["nodes"]:
    if n["name"] == "Search new contacts":
        n["parameters"]["jsonBody"] = n["parameters"]["jsonBody"].replace("'company']", "'company', 'message']")
json.dump(w, open(root / "workflows/intake-hubspot-phase1.json", "w"), indent=2)
print("ok")
