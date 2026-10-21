"""Compares the rows a fixture run wrote against fixtures `expected`. Usage: python3 scripts/compare_run.py <n8n execute output>
Checks outcome class, score, band, segment, owner (rules: 100%) and prints mismatches plus total cost."""
import json, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
fx = {f["id"]: f for f in json.load(open(root / "fixtures/n1-fixtures.json"))["fixtures"]}
s = open(sys.argv[1]).read()
d = json.loads(s[s.index("{\n"):s.rindex("}") + 1])
rows = [i["json"] for i in d["data"]["resultData"]["runData"]["Process lead"][0]["data"]["main"][0]]
mapo = {"draft_task_today": "contact_draft_pending", "draft_task_next_business_day": "contact_draft_pending"}
bad, cost = [], 0.0
for r in rows:
    f = fx[r["source_id"]]; e = f["expected"]; cost += float(r.get("cost_usd") or 0)
    want = {"outcome": mapo.get(e["outcome"], e["outcome"])}
    got = {"outcome": r["outcome"]}
    if e["contact_created"]:
        for k, rk in (("score", "score"), ("band", "band"), ("segment", "segment"), ("demo_owner", "demo_owner")):
            want[k] = str(e[k]); got[k] = str(r.get(rk, ""))
    if want != got: bad.append((r["source_id"], f["category"], want, got))
print(f"{len(rows)} rows, {len(rows) - len(bad)} match, total cost ${cost:.4f}")
for b in bad: print("MISMATCH", b[0], b[1], "\n  want", b[2], "\n  got ", b[3])
sys.exit(1 if bad or len(rows) != len(fx) else 0)
