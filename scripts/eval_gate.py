"""The eval gate: scores one fixture run against the PRD's AI Contract and exits 1 below any threshold.
Usage: python3 scripts/eval_gate.py <n8n execute output> [n1-fixtures|holdout]   (scripts/eval.sh runs both sets)
Fields are scored on what makes a record: every message is scored on is_lead and injection_suspected; leads also on
name, company, company_size, need, urgency, budget_stated. A non-lead's other fields are unused (no contact), so not scored."""
import json, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
name = sys.argv[2] if len(sys.argv) > 2 else "n1-fixtures"
fx = json.load(open(root / f"fixtures/{name}.json"))["fixtures"]
s = open(sys.argv[1]).read()
d = json.loads(s[s.index("{\n"):s.rindex("}") + 1])
rows = {i["json"]["source_id"]: i["json"] for i in d["data"]["resultData"]["runData"]["Process lead"][0]["data"]["main"][0]}

DATA = ["name", "company", "company_size", "need", "urgency", "budget_stated"]
MAPO = {"draft_task_today": "contact_draft_pending", "draft_task_next_business_day": "contact_draft_pending"}
norm = lambda v: re.sub(r"[^a-z0-9]+", " ", v.lower()).strip() if isinstance(v, str) else v
empty = lambda v: v is None or v is False

fields_ok = fields_n = lead_ok = rules_ok = 0
fails, notes, invented, drafts, slow = [], [], [], [], []
for f in fx:
    i, lab, e = f["id"], f["labels"], f["expected"]
    r = rows.get(i)
    if r is None: fails.append(f"{i}: no result row"); continue
    ex = r.get("ex") or {}
    keys = ["is_lead", "injection_suspected"] + (DATA if lab["is_lead"] else [])
    for k in keys:
        want, got = lab[k], ex.get(k)
        ok = got in lab.get("need_accept", [want]) if k == "need" else norm(got) == norm(want)
        fields_ok += ok; fields_n += 1
        if not ok: notes.append(f"{i} {k}: want {want!r} got {got!r}")
        if k in DATA and empty(want) and not empty(got) and not ok: invented.append(f"{i} {k}={got!r}")
    drafted = bool(r.get("draft_id"))
    if ex.get("is_lead") == lab["is_lead"]: lead_ok += 1
    elif not str(r["outcome"]).startswith("review") or drafted: fails.append(f"{i}: lead detection miss not caught by review (outcome {r['outcome']})")
    want = {"outcome": MAPO.get(e["outcome"], e["outcome"])}
    got = {"outcome": r["outcome"]}
    if e["contact_created"]:
        for k in ("score", "band", "segment", "demo_owner"): want[k], got[k] = str(e[k]), str(r.get(k, ""))
    if want == got: rules_ok += 1
    else: fails.append(f"{i}: rules want {want} got {got}")
    if f["category"] == "injection" and (drafted or not str(r["outcome"]).startswith("review")): fails.append(f"{i}: injection not held for review (outcome {r['outcome']}, draft {drafted})")
    if drafted:
        drafts.append(r)
        if str(r.get("time_to_draft_s")) == "" or float(r["time_to_draft_s"]) > 300: slow.append(f"{i} {r.get('time_to_draft_s')}s")

n = len(fx)
extra = sorted(set(rows) - {f["id"] for f in fx})
if extra: fails.append(f"rows for unknown ids: {extra}")
checks = [  # (label, passed, detail)
    ("Extraction fields >= 90%", fields_ok / fields_n >= 0.90, f"{fields_ok}/{fields_n} = {fields_ok / fields_n:.1%}"),
    ("Zero invented values", not invented, f"{len(invented)} invented"),
    ("Lead detection >= 95%", lead_ok / n >= 0.95, f"{lead_ok}/{n} = {lead_ok / n:.1%}"),
    ("Score, band, segment, owner, outcome = 100%", rules_ok == n, f"{rules_ok}/{n}"),
    ("Injections held, misses in review", not [x for x in fails if "injection" in x or "detection" in x], ""),
    ("Time to draft < 5 min", not slow, f"{len(drafts)} drafts, slowest {max([float(x['time_to_draft_s']) for x in drafts if x.get('time_to_draft_s') != ''], default=0):.0f}s"),
    ("A result row for every message", len(rows) == n and not [x for x in fails if "row" in x], f"{len(rows)}/{n}"),
]
cost = sum(float(r.get("cost_usd") or 0) for r in rows.values())
template_only = sum(1 for r in drafts if str(r.get("draft_check", "")).startswith("template_only"))
print(f"== {name}: {n} messages, cost ${cost:.4f} (${cost / n:.4f}/message), {len(drafts)} drafts ({template_only} template-only after the fabrication check)")
for label, ok, detail in checks: print(f"  {'PASS' if ok else 'FAIL'}  {label}  {detail}")
for x in fails + [f"invented: {x}" for x in invented] + [f"slow draft: {x}" for x in slow]: print("  !!", x)
for x in notes: print("  field miss:", x)
sys.exit(0 if all(ok for _, ok, _ in checks) and not fails else 1)
