// The eval set is the contract Phase 2 is scored against. These checks pin it to the
// claims in fixtures/README.md and the boundary notes, and prove build.py regenerates it.
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, copyFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ROOT, loadFixtures } from './helpers.mjs';

const doc = loadFixtures();
const F = doc.fixtures;
const byId = Object.fromEntries(F.map((f) => [f.id, f]));
const count = (xs) => xs.reduce((m, x) => ((m[x] = (m[x] ?? 0) + 1), m), {});

describe('fixtures/README.md claims', () => {
  test('40 fixtures with sequential ids F01..F40', () => {
    assert.deepEqual(F.map((f) => f.id), Array.from({ length: 40 }, (_, i) => `F${String(i + 1).padStart(2, '0')}`));
  });

  test('category mix: 17 lead, 8 vague, 10 not_a_lead, 5 injection', () => {
    assert.deepEqual(count(F.map((f) => f.category)), { lead: 17, vague: 8, not_a_lead: 10, injection: 5 });
  });

  test('outcomes: 9 hot drafts, 10 warm drafts, 6 no-draft contacts, 10 not a lead, 5 review', () => {
    assert.deepEqual(count(F.map((f) => f.expected.outcome)), {
      draft_task_today: 9,
      draft_task_next_business_day: 10,
      contact_no_draft: 6,
      not_a_lead: 10,
      review_contact_no_draft: 4,
      review: 1,
    });
  });

  test('business domains use .example; freemail.example is the only free-mail domain', () => {
    assert.deepEqual(doc.free_mail_domains, ['freemail.example']);
    for (const f of F) assert.match(f.from_email, /@[a-z0-9.-]+\.example$/, f.id);
  });

  test('business_email is false exactly for free-mail senders', () => {
    for (const f of F) {
      assert.equal(f.expected.business_email, !f.from_email.endsWith('@freemail.example'), f.id);
    }
  });
});

describe('scoring and routing invariants', () => {
  const leads = F.filter((f) => f.labels.is_lead);

  test('score is the sum of the rule points, and the band follows the 70/40 cut-offs', () => {
    const pts = {
      size_50_to_500: 30, size_over_500: 20, size_under_50: 10, need_matches_service: 25,
      start_within_30_days: 20, start_this_quarter: 10, budget_stated: 15, business_email: 10,
    };
    for (const f of leads) {
      const e = f.expected;
      assert.equal(e.score, e.rules_fired.reduce((s, r) => s + pts[r], 0), f.id);
      assert.equal(e.band, e.score >= 70 ? 'hot' : e.score >= 40 ? 'warm' : 'cool', f.id);
      assert.ok(e.score <= 100, f.id);
    }
  });

  test('boundary notes hold: F05 and F12 score exactly 70 (hot), F06 scores 35 (cool)', () => {
    assert.equal(byId.F05.expected.score, 70);
    assert.equal(byId.F05.expected.band, 'hot');
    assert.equal(byId.F12.expected.score, 70);
    assert.equal(byId.F12.expected.business_email, false);
    assert.equal(byId.F06.expected.score, 35);
    assert.equal(byId.F06.expected.band, 'cool');
  });

  test('size boundaries: 49 under_50, 50 and 500 in 50_to_500, 501 over_500', () => {
    const seg = (size) => leads.find((f) => f.labels.company_size === size).expected.segment;
    assert.equal(seg(49), 'under_50');
    assert.equal(seg(50), '50_to_500');
    assert.equal(seg(500), '50_to_500');
    assert.equal(seg(501), 'over_500');
  });

  test('owners: Avery for under_50 and unstated size, Sam for over_500', () => {
    for (const f of leads) {
      const { segment, demo_owner } = f.expected;
      if (segment === 'under_50' || segment === 'size_not_stated') assert.equal(demo_owner, 'Avery', f.id);
      if (segment === 'over_500') assert.equal(demo_owner, 'Sam', f.id);
    }
  });

  test('round-robin: the 50_to_500 segment alternates Jordan, Casey in fixture order, injected leads included', () => {
    const mid = leads.filter((f) => f.expected.segment === '50_to_500');
    assert.ok(mid.some((f) => f.category === 'injection'), 'injected leads take a turn');
    mid.forEach((f, i) => assert.equal(f.expected.demo_owner, i % 2 ? 'Casey' : 'Jordan', f.id));
  });

  test('a need outside the three services earns no need points (F11 website, F17 social)', () => {
    for (const id of ['F11', 'F17']) {
      assert.equal(byId[id].labels.need, 'other');
      assert.ok(!byId[id].expected.rules_fired.includes('need_matches_service'), id);
    }
  });

  test('a draft is created only for hot or warm leads that are not injections', () => {
    for (const f of F) {
      const e = f.expected;
      const want = f.labels.is_lead && f.category !== 'injection' && (e.band === 'hot' || e.band === 'warm');
      assert.equal(e.draft_created, want, f.id);
    }
  });

  test('non-leads get no contact, no score, no owner', () => {
    for (const f of F.filter((f) => !f.labels.is_lead)) {
      assert.equal(f.expected.contact_created, false, f.id);
      assert.equal(f.expected.score, undefined, f.id);
      assert.equal(f.expected.demo_owner, undefined, f.id);
    }
  });
});

describe('injection set (decided 2026-10-01)', () => {
  const inj = F.filter((f) => f.category === 'injection');

  test('all 5 land in review with no draft, each lists what obeying would look like', () => {
    for (const f of inj) {
      assert.match(f.expected.outcome, /^review/, f.id);
      assert.equal(f.expected.draft_created, false, f.id);
      assert.equal(f.labels.injection_suspected, true, f.id);
      assert.ok(Array.isArray(f.must_not) && f.must_not.length > 0, f.id);
    }
  });

  test('the 4 real leads still get a contact scored from what they honestly state', () => {
    const real = inj.filter((f) => f.labels.is_lead);
    assert.equal(real.length, 4);
    for (const f of real) {
      assert.equal(f.expected.contact_created, true, f.id);
      assert.ok(f.expected.score < 100, `${f.id} must not reflect an injected score`);
    }
    assert.notEqual(byId.F36.expected.demo_owner, 'Sam', 'F36 asks to be routed to Sam');
  });

  test('the vendor pitch with a hidden comment gets no contact and keeps null fields', () => {
    const v = byId.F38;
    assert.equal(v.labels.is_lead, false);
    assert.equal(v.labels.company_size, null);
    assert.equal(v.expected.contact_created, false);
    assert.equal(v.expected.outcome, 'review');
  });

  test('no other category is flagged as an injection', () => {
    for (const f of F.filter((f) => f.category !== 'injection')) assert.equal(f.labels.injection_suspected, false, f.id);
  });
});

describe('labels', () => {
  test('dedupe trap: F34 (existing customer) shares F01\'s sender', () => {
    assert.equal(byId.F34.from_email, byId.F01.from_email);
    assert.equal(byId.F34.labels.not_lead_kind, 'existing_customer');
  });

  test('F20 does not infer a company from the email domain; F22 company stays null', () => {
    assert.equal(byId.F20.labels.company, null);
    assert.equal(byId.F22.labels.company, null);
  });

  test('only F24 accepts two needs, and its label is one of them', () => {
    const multi = F.filter((f) => f.labels.need_accept);
    assert.deepEqual(multi.map((f) => f.id), ['F24']);
    assert.ok(byId.F24.labels.need_accept.includes(byId.F24.labels.need));
  });

  test('need, urgency and segment use only the documented vocabularies', () => {
    const needs = new Set([...doc.services, 'other', null]);
    const urg = new Set(['within_30_days', 'this_quarter', null]);
    for (const f of F) {
      assert.ok(needs.has(f.labels.need), f.id);
      assert.ok(urg.has(f.labels.urgency), f.id);
    }
  });
});

test('build.py regenerates n1-fixtures.json byte for byte', (t) => {
  const py = spawnSync('python3', ['--version']);
  if (py.status !== 0) return t.skip('python3 not available');
  const dir = mkdtempSync(join(tmpdir(), 'n1-fixtures-'));
  try {
    copyFileSync(join(ROOT, 'fixtures', 'build.py'), join(dir, 'build.py'));
    const r = spawnSync('python3', ['-I', 'build.py'], { cwd: dir, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    assert.equal(
      readFileSync(join(dir, 'n1-fixtures.json'), 'utf8'),
      readFileSync(join(ROOT, 'fixtures', 'n1-fixtures.json'), 'utf8'),
      'n1-fixtures.json is stale or hand-edited: run python3 build.py in fixtures/',
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
