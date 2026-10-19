// Runs every fixture's labels through the rules and demands an exact match to `expected` (PRD: score and route are rules, 100%).
const test = require('node:test');
const assert = require('node:assert');
const { score, band, route } = require('../lib/scoring');
const rd = (n) => require(`../rules/${n}.json`);
const fx = require('../fixtures/n1-fixtures.json');

test('score, band, segment, owner match every fixture that reaches routing', () => {
  const counts = {};
  let checked = 0;
  for (const f of fx.fixtures) {
    if (!f.expected.contact_created) continue;
    const business = !fx.free_mail_domains.includes(f.from_email.split('@')[1]);
    const s = score(f.labels, rd('score_rules'), business);
    const r = route(f.labels.company_size, rd('routing'), counts);
    counts[r.segment] = (counts[r.segment] || 0) + 1;
    const got = { score: s.score, rules_fired: s.rules_fired, band: band(s.score, rd('bands')).band, segment: r.segment, demo_owner: r.demo_owner };
    const want = Object.fromEntries(Object.keys(got).map((k) => [k, f.expected[k]]));
    assert.deepStrictEqual(got, want, f.id);
    checked++;
  }
  assert.strictEqual(checked, fx.fixtures.filter((f) => f.expected.contact_created).length);
  assert.ok(checked >= 20, `only ${checked} fixtures reached routing`);
});

test('boundaries: 49/50/500/501 and band edges 39/40/69/70', () => {
  const rules = rd('score_rules');
  const pts = (size) => score({ company_size: size }, rules, false).score;
  assert.deepStrictEqual([49, 50, 500, 501].map(pts), [10, 30, 30, 20]);
  const bands = rd('bands');
  assert.deepStrictEqual([39, 40, 69, 70].map((n) => band(n, bands).band), ['cool', 'warm', 'warm', 'hot']);
  assert.strictEqual(route(null, rd('routing'), {}).segment, 'size_not_stated');
});
