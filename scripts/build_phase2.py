"""Generates the Phase 2 workflows: process-lead (new), and rewires the two intakes and the run-log writer.
The logic lives in lib/*.js (unit-tested); this embeds it into n8n Code nodes so tests and workflow cannot drift.
Usage: python3 scripts/build_phase2.py"""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
SHEET = "1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY"
GS = {"googleSheetsOAuth2Api": {"id": "McOy4auCNkFX0Os2", "name": "Google Sheets account"}}
AN = {"anthropicApi": {"id": "iX5UtPD5bryOqgFt", "name": "Anthropic account"}}
GM = {"gmailOAuth2": {"id": "GGGxY4DRdE9giH2x", "name": "Gmail account"}}
HS = {"hubspotAppToken": {"id": "u1WBi64R7zas6Zfn", "name": "HubSpot Service Key account"}}
READ_RETRY = dict(retryOnFail=True, maxTries=3, waitBetweenTries=2000)
PROCESS_ID, WRITER_ID = "n1ProcessLead0001", "n1RunLogWriter01"

def bundle():
    """scoring.js + lead.js as one prelude defining `L` (lead.js exports) for a Code node."""
    out = "const __lib = {}; const require = (p) => __lib[p];\n"
    for n in ("scoring", "lead", "draft"):
        out += f"__lib['./{n}'] = (() => {{ const module = {{ exports: {{}} }};\n{(root / 'lib' / (n + '.js')).read_text()}\nreturn module.exports; }})();\n"
    return out + "const L = __lib['./lead']; const D = __lib['./draft'];\n"
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
RUNS = ["time", "source", "source_id", "outcome", "time_to_draft_s", "cost_usd", "error", "score", "band", "segment", "demo_owner", "input_tokens", "output_tokens", "draft_id", "thread_id", "draft_check", "task_id", "approval", "approval_at"]
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
  return { json: { idx, msg, allowed, started_at: $now.toISO(), request: allowed ? L.buildRequest(msg, cfg.extract_model) : null } };
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
nodes.append(code("Build upsert", [2420, 0], "return [{ json: { inputs: L.upsertInputs($input.all().map((i) => i.json)) } }];", once=True))
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
CONTINUE = dict(onError="continueRegularOutput", retryOnFail=False)  # a write that throws mid-batch would re-run the batch next poll and duplicate drafts
nodes.append(code("Draft prep", [3300, -300], """
// Leads that get a draft: decided contact_draft_pending, not already drafted (replay guard on the run log's draft_id).
const T = L.tablesFromRanges($('Load tables').first().json.valueRanges);
const cfg = D.cfgOf(T);
const drafted = new Set(T.runs.filter((r) => r.draft_id).map((r) => r.source_id));
const ids = Object.fromEntries(($('Upsert contacts').first().json.results ?? []).map((r) => [String(r.properties?.email).toLowerCase(), r.id]));
const msgs = Object.fromEntries($('When called').all().map((i) => [i.json.source_id, i.json]));
const todo = $('Decide').all().map((i) => i.json).filter((d) => d.outcome === 'contact_draft_pending' && !drafted.has(d.source_id))
  .map((d) => ({ d, msg: msgs[d.source_id], contact_id: ids[L.hubspotEmail(d.from_email).toLowerCase()], request: D.buildDraftRequest(msgs[d.source_id], cfg.draft_model) }));
return [{ json: { todo } }];""", once=True))
nodes.append(node("Any drafts?", "n8n-nodes-base.if", 2.2, [3520, -300], {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
    "conditions": [{"id": "c3", "leftValue": "={{ $json.todo.length }}", "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}], "combinator": "and"}, "options": {}}))
nodes.append(code("Split drafts", [3740, -400], "return $json.todo.map((t) => ({ json: t }));", once=True))
nodes.append(node("Write ack", "n8n-nodes-base.httpRequest", 4.2, [3960, -400], {"method": "POST", "url": "https://api.anthropic.com/v1/messages", "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]}, "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}"},
    credentials=AN, onError="continueRegularOutput", retryOnFail=True, maxTries=2, waitBetweenTries=3000))  # a read: retry is safe; failure -> template-only draft
nodes.append(code("Build draft", [4180, -400], """
// The model's sentence is checked by rules; a rejected or failed sentence leaves the template-only draft.
const t = $('Split drafts').item.json;
const cfg = D.cfgOf(L.tablesFromRanges($('Load tables').first().json.valueRanges));
const text = $json.content?.[0]?.text;
const c = text === undefined ? { ok: false, reason: 'model error: ' + String($json.error?.message ?? $json.error ?? 'no content').slice(0, 120), text: '' } : D.checkAck(text);
const { subject, body } = D.fillTemplate(t.d, c.ok ? c.text : '', cfg);
const raw = D.mimeRaw({ to: L.hubspotEmail(t.d.from_email), subject, body, inReplyTo: t.msg.message_id || '' });
const draft = { message: { raw } };
if (t.msg.thread_id) draft.message.threadId = t.msg.thread_id;
return { json: { ...t, draft, draft_check: c.ok ? 'ok' : `template_only: ${c.reason} | ${String(c.text).slice(0, 250)}`, rejected_text: c.ok ? '' : c.text, usage: $json.usage ?? { input_tokens: 0, output_tokens: 0 } } };""", each=True))
nodes.append(node("Create draft", "n8n-nodes-base.httpRequest", 4.2, [4400, -400], {"method": "POST", "url": "https://gmail.googleapis.com/gmail/v1/users/me/drafts", "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2",
    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.draft) }}"}, credentials=GM, **CONTINUE))
nodes.append(code("Build tasks", [4620, -400], """
const T = L.tablesFromRanges($('Load tables').first().json.valueRanges);
const cfg = D.cfgOf(T);
const now = $now.toISO();
const built = $('Build draft').all().map((i) => i.json);
const out = $input.all().map((i, k) => {
  const b = built[k], r = i.json, ok = !!r.id;
  const started = Date.parse(b.msg.received_at || $('Prep').first().json.started_at);
  return { source_id: b.d.source_id, d: b.d, contact_id: b.contact_id, draft_ok: ok, draft_id: r.id ?? '', draft_msg_id: r.message?.id ?? '', thread_id: r.message?.threadId ?? '',
    draft_error: ok ? '' : String(r.error?.message ?? JSON.stringify(r.error ?? r)).slice(0, 200), draft_check: b.draft_check, rejected_text: b.rejected_text, usage: b.usage,
    time_to_draft_s: ok ? Math.round((Date.now() - started) / 1000) : '' };
});
const inputs = out.filter((o) => o.draft_ok && o.contact_id).map((o) => D.taskInput(o.d, o.contact_id, o.draft_msg_id, now, cfg.hubspot_owner_id));
return [{ json: { out, body: { inputs } } }];""", once=True))
nodes.append(node("Create tasks", "n8n-nodes-base.httpRequest", 4.2, [4840, -400], {"method": "POST", "url": "https://api.hubapi.com/crm/v3/objects/tasks/batch/create", "authentication": "predefinedCredentialType", "nodeCredentialType": "hubspotAppToken",
    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.body) }}"}, credentials=HS, **CONTINUE))
nodes.append(code("Draft results", [5060, -400], """
// Batch create returns results in input order. A failed task batch is logged per lead (task_id 'error: ...') and reviewed, never retried.
const { out } = $('Build tasks').first().json;
const r = $json;
const ok = Array.isArray(r.results) && r.status === 'COMPLETE';
let k = 0;
for (const o of out) {
  if (!(o.draft_ok && o.contact_id)) { o.task_id = ''; continue; }
  o.task_id = ok ? r.results[k++]?.id ?? '' : 'error: ' + String(r.error?.message ?? r.message ?? JSON.stringify(r)).slice(0, 150);
}
return [{ json: { drafts: out } }];""", once=True))
nodes.append(node("Contacts done", "n8n-nodes-base.noOp", 1, [3300, 0], {}))
nodes.append(code("Review rows", [3520, -100], """
let drafts = {}; try { drafts = Object.fromEntries($('Draft results').first().json.drafts.map((o) => [o.source_id, o])); } catch (e) { /* no drafts this run */ }
const why = (d) => d.review ? d.review_reason : drafts[d.source_id]?.draft_error ? 'draft not created: ' + drafts[d.source_id].draft_error
  : String(drafts[d.source_id]?.task_id ?? '').startsWith('error') ? 'HubSpot task not created: ' + drafts[d.source_id].task_id : '';
return $('Decide').all().map((i) => i.json).filter((d) => why(d)).map((d) => ({ json: { source: d.source, source_id: d.source_id, from: d.from_email, subject: d.subject, reason: why(d), raw_output: d.raw || '' } }));""", once=True))
nodes.append(sheets_upsert("Write review", [3740, -100], "review", REVIEW, "source_id"))
nodes.append(code("Log rows", [3520, 120], """
let drafts = {}; try { drafts = Object.fromEntries($('Draft results').first().json.drafts.map((o) => [o.source_id, o])); } catch (e) { /* no drafts this run */ }
const T = L.tablesFromRanges($('Load tables').first().json.valueRanges);
const cfg = D.cfgOf(T);
// A replayed lead that was already drafted keeps its draft, task and approval fields (Draft prep skipped it).
const prior = Object.fromEntries(T.runs.filter((r) => r.draft_id).map((r) => [r.source_id, r]));
const KEEP = ['time_to_draft_s', 'draft_id', 'thread_id', 'draft_check', 'task_id', 'approval', 'approval_at'];
return $('Decide').all().map((i) => i.json).map((d) => {
  const x = drafts[d.source_id];
  const p = !x && prior[d.source_id];
  if (p) return { json: { source: d.source, source_id: d.source_id, outcome: p.outcome, cost_usd: d.cost_usd, error: '', score: d.score ?? '', band: d.band ?? '', segment: d.segment ?? '', demo_owner: d.demo_owner ?? '',
    input_tokens: d.input_tokens, output_tokens: d.output_tokens, ...Object.fromEntries(KEEP.map((k) => [k, p[k] ?? ''])) } };
  const u = x?.usage ?? { input_tokens: 0, output_tokens: 0 };
  const cost = d.cost_usd + (x ? L.costUsd(u, T.rates, cfg.draft_model) : 0);
  return { json: { source: d.source, source_id: d.source_id, outcome: x?.draft_error ? 'contact_draft_failed' : d.outcome, time_to_draft_s: x?.time_to_draft_s ?? '', cost_usd: Number(cost.toFixed(6)), error: x?.draft_error ?? '',
    score: d.score ?? '', band: d.band ?? '', segment: d.segment ?? '', demo_owner: d.demo_owner ?? '', input_tokens: d.input_tokens + (u.input_tokens ?? 0), output_tokens: d.output_tokens + (u.output_tokens ?? 0),
    draft_id: x?.draft_id ?? '', thread_id: x?.thread_id ?? '', draft_check: x?.draft_check ?? '', task_id: x?.task_id ?? '', approval: x?.draft_id ? 'pending' : '', approval_at: '' } };
});""", once=True))
nodes.append(node("Write run log", "n8n-nodes-base.executeWorkflow", 1.2, [3740, 120], {"source": "database", "workflowId": {"__rl": True, "value": WRITER_ID, "mode": "id"}, "options": {}}))
# Runs last, so it is what a caller receives: the log row plus the extraction, which the eval gate scores (the sheet never stores it).
nodes.append(code("Result", [3960, 120], """
const dec = Object.fromEntries($('Decide').all().map((i) => [i.json.source_id, i.json]));
return $('Log rows').all().map((i) => ({ json: { ...i.json, ex: dec[i.json.source_id]?.ex ?? null } }));""", once=True))
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
link(c, "Upsert contacts", "Verify upsert"); link(c, "Verify upsert", "Draft prep"); link(c, "Draft prep", "Any drafts?")
link(c, "Any drafts?", "Split drafts", 0); link(c, "Any drafts?", "Contacts done", 1)
for a, b in [("Split drafts", "Write ack"), ("Write ack", "Build draft"), ("Build draft", "Create draft"), ("Create draft", "Build tasks"), ("Build tasks", "Create tasks"), ("Create tasks", "Draft results"), ("Draft results", "Contacts done")]: link(c, a, b)
link(c, "Contacts done", "Review rows"); link(c, "Contacts done", "Log rows")
link(c, "Review rows", "Write review"); link(c, "Log rows", "Write run log"); link(c, "Write run log", "Result")
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
      thread_id: i.json.threadId ?? '', message_id: i.json.messageId ?? '', received_at: i.json.date ?? '',
    }};
  });""")
rewire("workflows/intake-hubspot-phase1.json", """// ponytail: looks back 24h and dedupes against the run log, so a missed poll or a failed run is retried. Longer outages need a wider window.
const rows = $('Read run log').all().map(i => i.json).filter(r => r.source_id);
const done = new Set(rows.filter(r => r.outcome !== 'error').map(r => r.source_id));
return ($('Search new contacts').first().json.results ?? [])
  .filter(c => !done.has('hubspot:' + c.id))
  .map(c => ({ json: { source: 'hubspot', source_id: 'hubspot:' + c.id, from_email: c.properties?.email ?? '',
    subject: 'HubSpot form', body: [c.properties?.firstname, c.properties?.lastname].filter(Boolean).join(' ') + '\\n' + (c.properties?.company ?? '') + '\\n\\n' + (c.properties?.message ?? ''), received_at: c.createdAt ?? '' } }));""")
# the HubSpot search must also return the form message
w = json.load(open(root / "workflows/intake-hubspot-phase1.json"))
for n in w["nodes"]:
    if n["name"] == "Search new contacts":
        n["parameters"]["jsonBody"] = n["parameters"]["jsonBody"].replace("'company']", "'company', 'message']")
json.dump(w, open(root / "workflows/intake-hubspot-phase1.json", "w"), indent=2)
# ---------------- approval check (P0-7): records sent / discarded against the run, from Gmail state. Never sends.
NEVER_ERR = {"response": {"response": {"neverError": True}}}  # a 404 is an answer here (draft gone), not a failure
def gmail_get(name, pos, url):
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, {"method": "GET", "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2", "options": NEVER_ERR}, credentials=GM, **READ_RETRY)
an = [node("Every 30 minutes", "n8n-nodes-base.scheduleTrigger", 1.2, [0, -100], {"rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]}}),
      node("Run now (manual)", "n8n-nodes-base.manualTrigger", 1, [0, 100], {}),
      node("Read run log", "n8n-nodes-base.googleSheets", 4.7, [220, 0], {"documentId": {"__rl": True, "value": SHEET, "mode": "id"}, "sheetName": {"__rl": True, "value": "runs", "mode": "name"}, "options": {}}, credentials=GS, **READ_RETRY),
      code("Pending", [440, 0], "return $input.all().map((i) => i.json).filter((r) => r.approval === 'pending' && r.draft_id).map((r) => ({ json: { source_id: r.source_id, draft_id: r.draft_id, thread_id: r.thread_id, time: r.time } }));", once=True),
      gmail_get("Get draft", [660, 0], "=https://gmail.googleapis.com/gmail/v1/users/me/drafts/{{ $json.draft_id }}?format=minimal"),
      gmail_get("Get thread", [880, 0], "=https://gmail.googleapis.com/gmail/v1/users/me/threads/{{ $('Pending').item.json.thread_id }}?format=minimal"),
      code("Decide approval", [1100, 0], """
// Draft present -> still pending. Gone -> sent if the thread holds a SENT message from after the draft, else discarded.
// Any other error (auth, quota) throws: guessing 'discarded' from a failed read would record a false outcome.
return $('Pending').all().map((p, k) => {
  const dr = $('Get draft').all()[k].json, th = $('Get thread').all()[k].json;
  if (dr.error && dr.error.code !== 404) throw new Error(`Gmail draft read failed for ${p.json.source_id}: ${dr.error.message}`);
  if (th.error && th.error.code !== 404) throw new Error(`Gmail thread read failed for ${p.json.source_id}: ${th.error.message}`);
  const state = D.approvalState(!!dr.id, th.messages, Date.parse(p.json.time));
  return { json: { source_id: p.json.source_id, approval: state } };
}).filter((i) => i.json.approval !== 'pending');""", once=True),
      sheets_upsert("Record approval", [1320, 0], "runs", ["source_id", "approval", "approval_at"], "source_id")]
an[-1]["parameters"]["columns"]["value"]["approval_at"] = "={{ $now.toISO() }}"
ac = {}
for a_, b_ in [("Every 30 minutes", "Read run log"), ("Run now (manual)", "Read run log"), ("Read run log", "Pending"), ("Pending", "Get draft"), ("Get draft", "Get thread"), ("Get thread", "Decide approval"), ("Decide approval", "Record approval")]: link(ac, a_, b_)
json.dump(wf("n1ApprovalCheck01", "N1 approval check (phase 3)", an, ac, {"errorWorkflow": "n1ErrorHandler01"}), open(root / "workflows/approval-check.json", "w"), indent=2)
print("ok")
