// Executes the JavaScript inside the workflows' Code nodes against mocked inputs.
// These nodes hold the spine's only business logic in Phase 1: dedupe and alert throttling.
import { test, describe, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { workflow, node, runCodeNode } from './helpers.mjs';

const gmail = workflow('intake-phase1.json');
const hubspot = workflow('intake-hubspot-phase1.json');
const errorHandler = workflow('error-handler.json');

// What the Sheets read node emits for an empty `runs` tab: alwaysOutputData gives one empty item.
const EMPTY_LOG = [{}];

const mail = (id, address = 'lead@example.com', subject = 'Hello') => ({
  id,
  subject,
  from: { value: [{ address, name: 'Lead' }] },
});

describe('Gmail intake: Pick unseen', () => {
  const pick = node(gmail, 'Pick unseen');
  const run = (mailItems, logRows) =>
    runCodeNode(pick, { nodes: { 'List labelled mail': mailItems, 'Read run log': logRows } });

  test('every message is new on an empty log', () => {
    const out = run([mail('a1'), mail('b2')], EMPTY_LOG);
    assert.deepEqual(out.map((o) => o.source_id), ['a1', 'b2']);
  });

  test('shapes the item the log row and Phase 2 need', () => {
    const [o] = run([mail('a1', 'dana@northwind.example', 'CRM cleanup')], EMPTY_LOG);
    assert.deepEqual(o, { source: 'gmail', source_id: 'a1', from: 'dana@northwind.example', subject: 'CRM cleanup' });
  });

  test('replay-safe: a message already logged with a non-error outcome is skipped', () => {
    const out = run([mail('a1'), mail('b2')], [{ source_id: 'a1', outcome: 'spine_ok' }]);
    assert.deepEqual(out.map((o) => o.source_id), ['b2']);
  });

  test('second poll after a clean run picks nothing', () => {
    const first = run([mail('a1'), mail('b2')], EMPTY_LOG);
    const log = first.map((o) => ({ source_id: o.source_id, outcome: 'spine_ok' }));
    assert.deepEqual(run([mail('a1'), mail('b2')], log), []);
  });

  test('a row with outcome "error" does not count as done, so the message is retried', () => {
    const out = run([mail('a1')], [{ source_id: 'a1', outcome: 'error' }]);
    assert.deepEqual(out.map((o) => o.source_id), ['a1']);
  });

  test('dedupe key is the message id, not the sender (F01 and F34 share a sender)', () => {
    const same = 'dana.whitfield@northwindlogistics.example';
    const out = run([mail('m1', same), mail('m2', same)], [{ source_id: 'm1', outcome: 'spine_ok' }]);
    assert.deepEqual(out.map((o) => o.source_id), ['m2']);
  });

  test('an all-digit id read back from Sheets as a number still dedupes', () => {
    const out = run([mail('1234567890')], [{ source_id: 1234567890, outcome: 'spine_ok' }]);
    assert.deepEqual(out, []);
  });

  test('missing sender or subject degrades to empty strings instead of throwing', () => {
    const [o] = run([{ id: 'x9' }], EMPTY_LOG);
    assert.equal(o.from, '');
    assert.equal(o.subject, '');
  });

  test('blank log rows (no source_id) are ignored', () => {
    const out = run([mail('a1')], [{}, { source_id: '', outcome: 'spine_ok' }]);
    assert.deepEqual(out.map((o) => o.source_id), ['a1']);
  });
});

describe('HubSpot intake: Pick unseen', () => {
  const pick = node(hubspot, 'Pick unseen');
  const run = (results, logRows) =>
    runCodeNode(pick, { nodes: { 'Search new contacts': [{ results }], 'Read run log': logRows } });
  const contact = (id, email) => ({ id, properties: { email } });

  test('prefixes source ids with hubspot: so they cannot collide with Gmail ids', () => {
    const out = run([contact('101', 'a@b.example')], EMPTY_LOG);
    assert.deepEqual(out, [{ source: 'hubspot', source_id: 'hubspot:101', email: 'a@b.example' }]);
  });

  test('skips contacts already logged, retries errored ones', () => {
    const out = run(
      [contact('1'), contact('2'), contact('3')],
      [
        { source_id: 'hubspot:1', outcome: 'spine_ok' },
        { source_id: 'hubspot:2', outcome: 'error' },
      ],
    );
    assert.deepEqual(out.map((o) => o.source_id), ['hubspot:2', 'hubspot:3']);
  });

  test('a Gmail row with the same bare id does not hide a HubSpot contact', () => {
    const out = run([contact('101')], [{ source_id: '101', outcome: 'spine_ok' }]);
    assert.deepEqual(out.map((o) => o.source_id), ['hubspot:101']);
  });

  test('a search response without results yields no items', () => {
    assert.deepEqual(run(undefined, EMPTY_LOG), []);
  });

  test('a contact without an email property gets an empty email', () => {
    const [o] = run([{ id: '7' }], EMPTY_LOG);
    assert.equal(o.email, '');
  });
});

describe('Error handler: Shape and throttle', () => {
  const shape = node(errorHandler, 'Shape and throttle');
  const realNow = Date.now;
  afterEach(() => {
    Date.now = realNow;
  });
  const failure = (over = {}) => ({
    workflow: { name: 'N1 intake (phase 1: spine)' },
    execution: { id: 42, lastNodeExecuted: 'Read run log', error: { message: 'quota exceeded' } },
    ...over,
  });
  const at = (ms, staticData, json = failure()) => {
    Date.now = () => ms;
    return runCodeNode(shape, { json, staticData })[0];
  };

  test('shapes a run-log row naming the workflow, execution, step and message', () => {
    const row = at(1_000_000, {});
    assert.equal(row.source, 'N1 intake (phase 1: spine)');
    assert.equal(row.source_id, 'execution 42');
    assert.equal(row.outcome, 'error');
    assert.equal(row.error, 'Read run log: quota exceeded');
    assert.equal(row.subject, 'n8n alert: N1 intake (phase 1: spine) failed at Read run log');
  });

  test('first failure sends; failures inside 15 minutes do not; the window reopens after', () => {
    const s = {};
    const t0 = 1_700_000_000_000;
    const min = 60 * 1000;
    assert.equal(at(t0, s).send, true);
    assert.equal(at(t0 + 1 * min, s).send, false);
    assert.equal(at(t0 + 15 * min - 1, s).send, false);
    assert.equal(at(t0 + 15 * min, s).send, true);
    assert.equal(s.lastAlert, t0 + 15 * min);
  });

  test('a suppressed alert does not extend the quiet window', () => {
    const s = {};
    const t0 = 1_700_000_000_000;
    at(t0, s);
    at(t0 + 10 * 60 * 1000, s); // suppressed
    assert.equal(s.lastAlert, t0);
  });

  test('every failure still produces a row to log, sent or not', () => {
    const s = {};
    const rows = [0, 1, 2].map((i) => at(1_700_000_000_000 + i * 60 * 1000, s));
    assert.deepEqual(rows.map((r) => r.outcome), ['error', 'error', 'error']);
    assert.deepEqual(rows.map((r) => r.send), [true, false, false]);
  });

  test('a malformed error payload still yields a loggable row', () => {
    const row = at(1, {}, {});
    assert.equal(row.source, 'unknown');
    assert.equal(row.source_id, 'execution ?');
    assert.equal(row.error, '?: unknown');
  });
});
