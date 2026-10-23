const test = require('node:test');
const assert = require('node:assert');
const L = require('../lib/lead');
const rd = (n) => require(`../rules/${n}.json`);
const fx = require('../fixtures/n1-fixtures.json');
const tables = { config: rd('config'), score_rules: rd('score_rules'), bands: rd('bands'), routing: rd('routing'), rates: rd('rates') };

// Feed each fixture's LABELS in as if the model had returned them perfectly, in fixture order on a fresh log.
// Proves the decision layer alone matches `expected`; the model's own accuracy is the Phase 4 eval.
test('decideBatch on perfect extractions matches expected outcome, score, owner, contact for all 40', () => {
  const items = fx.fixtures.map((f) => ({ msg: { source: 'fixture', source_id: f.id, from_email: f.from_email, subject: f.subject }, ex: f.labels }));
  const out = L.decideBatch(items, tables, []);
  const map = { draft_task_today: 'contact_draft_pending', draft_task_next_business_day: 'contact_draft_pending' };
  out.forEach((d, i) => {
    const e = fx.fixtures[i].expected;
    assert.strictEqual(d.outcome, map[e.outcome] ?? e.outcome, fx.fixtures[i].id);
    assert.strictEqual(d.contact, e.contact_created, fx.fixtures[i].id);
    if (e.contact_created) {
      assert.strictEqual(d.score, e.score, fx.fixtures[i].id);
      assert.strictEqual(d.demo_owner, e.demo_owner, fx.fixtures[i].id);
      assert.strictEqual(d.band, e.band, fx.fixtures[i].id);
    }
  });
});

test('round-robin continues from the run log across batches', () => {
  const lead = (id) => ({ msg: { source: 'x', source_id: id, from_email: 'a@b.example', subject: '' }, ex: { ...fx.fixtures[0].labels } });
  const first = L.decideBatch([lead('1')], tables, []);
  const second = L.decideBatch([lead('2')], tables, [{ segment: first[0].segment, outcome: first[0].outcome }]);
  assert.deepStrictEqual([first[0].demo_owner, second[0].demo_owner], ['Jordan', 'Casey']);
});

test('validation: good JSON passes, fences stripped, wrong types and extras fail', () => {
  const good = { name: 'A B', company: 'C', company_size: 10, need: 'crm_cleanup', urgency: null, budget_stated: false, is_lead: true, not_lead_kind: null, injection_suspected: false };
  assert.ok(L.parseExtraction(JSON.stringify(good)).ok);
  assert.ok(L.parseExtraction('```json\n' + JSON.stringify(good) + '\n```').ok);
  assert.ok(!L.parseExtraction(JSON.stringify({ ...good, company_size: '10' })).ok);
  assert.ok(!L.parseExtraction(JSON.stringify({ ...good, need: 'sales' })).ok);
  assert.ok(!L.parseExtraction('APPROVED').ok);
  assert.ok(!L.parseExtraction(JSON.stringify({ ...good, is_lead: undefined })).ok);
  assert.ok(!L.parseExtraction('[1]').ok);
});

test('cost: tokens priced from the rate table, unknown model throws', () => {
  assert.strictEqual(L.costUsd({ input_tokens: 1_000_000, output_tokens: 1_000_000 }, tables.rates, 'claude-haiku-4-5-20251001'), 6);
  assert.throws(() => L.costUsd({ input_tokens: 1 }, tables.rates, 'nope'));
});

test('demo guard refuses real-looking addresses and allows synthetic ones', () => {
  assert.ok(L.demoAllowed('a@example.com') && L.demoAllowed('a@northwind.example') && !L.demoAllowed('a@gmail.com') && !L.demoAllowed('a@example.com.evil.io'));
  const out = L.decideBatch([{ msg: { source: 'x', source_id: '1', from_email: 'real@gmail.com' }, ex: fx.fixtures[0].labels }], tables, []);
  assert.strictEqual(out[0].outcome, 'skipped_demo_guard');
});

test('tablesFromRanges pads short rows; todayCost sums only today', () => {
  const vr = [{ values: [['key', 'value'], ['a', '1']] }, {}, {}, {}, {}, { values: [['time', 'cost_usd'], ['2026-10-20T09:00:00-04:00', '0.5'], ['2026-10-19T09:00:00-04:00', '9'], ['2026-10-20T10:00:00-04:00']] }];
  const t = L.tablesFromRanges(vr);
  assert.deepStrictEqual(t.config, [{ key: 'a', value: '1' }]);
  assert.deepStrictEqual(t.bands, []);
  assert.strictEqual(L.todayCost(t.runs, '2026-10-20'), 0.5);
});

test('hubspotEmail maps the .example TLD to example.com and leaves real-format addresses alone', () => {
  assert.strictEqual(L.hubspotEmail('a@northwind.example'), 'a@northwind.example.com');
  assert.strictEqual(L.hubspotEmail('a@example.com'), 'a@example.com');
  assert.ok(L.demoAllowed('a@northwind.example.com'));
  const d = L.decideBatch([{ msg: { source: 'x', source_id: '1', from_email: 'dana@northwind.example' }, ex: { ...fx.fixtures[0].labels, name: 'Dana Whitfield' } }], tables, [])[0];
  assert.strictEqual(L.contactInput(d).id, 'dana@northwind.example.com');
});

test('upsertInputs: one sender twice in a batch gives one record, later message wins', () => {
  const lead = (id, company) => ({ msg: { source: 'gmail', source_id: id, from_email: 'Ravi@Calder.example', subject: '' }, ex: { ...fx.fixtures[0].labels, company } });
  const out = L.upsertInputs(L.decideBatch([lead('1', 'Old Co'), lead('2', 'New Co')], tables, []));
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].properties.company, 'New Co');
});
