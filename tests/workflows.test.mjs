// Static lint of the n8n workflow exports: wiring, cross-workflow references, the
// write/retry rule from NEXT.md, the run-log schema, and what must never be committed.
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { ROOT, loadWorkflows, workflow, node, isTrigger } from './helpers.mjs';

const all = loadWorkflows();
const ids = new Set(all.map(({ wf }) => wf.id));
const importScript = readFileSync(join(ROOT, 'scripts', 'import.sh'), 'utf8');

const SHEET_ID = '1tf-R3Nx1leSg4i4rBwCq8XzItWzUk-qID06-js_AOcY';
const RUN_COLUMNS = ['time', 'source', 'source_id', 'outcome', 'time_to_draft_s', 'cost_usd', 'error'];

describe('every workflow export', () => {
  test('workflow ids are unique', () => {
    assert.equal(ids.size, all.length);
  });

  for (const { file, wf } of all) {
    describe(file, () => {
      test('has id, name, nodes and connections, and is exported inactive', () => {
        assert.ok(wf.id && wf.name && Array.isArray(wf.nodes) && wf.connections);
        assert.equal(wf.active, false, 'activation happens on the instance, never via the export');
      });

      test('node names are unique', () => {
        const names = wf.nodes.map((n) => n.name);
        assert.equal(new Set(names).size, names.length);
      });

      test('every connection points at nodes that exist', () => {
        const names = new Set(wf.nodes.map((n) => n.name));
        for (const [from, outputs] of Object.entries(wf.connections)) {
          assert.ok(names.has(from), `connection from missing node "${from}"`);
          for (const branch of outputs.main ?? []) {
            for (const c of branch ?? []) assert.ok(names.has(c.node), `connection to missing node "${c.node}"`);
          }
        }
      });

      test('every non-trigger node is reachable (no orphaned steps)', () => {
        const targets = new Set(
          Object.values(wf.connections).flatMap((o) => (o.main ?? []).flat().map((c) => c.node)),
        );
        for (const n of wf.nodes) {
          if (!isTrigger(n)) assert.ok(targets.has(n.name), `"${n.name}" has no incoming connection`);
        }
      });

      test('credentials are references (id + name) only, never inline secrets', () => {
        for (const n of wf.nodes) {
          for (const [type, ref] of Object.entries(n.credentials ?? {})) {
            assert.deepEqual(Object.keys(ref).sort(), ['id', 'name'], `${n.name} ${type}`);
          }
        }
        const text = JSON.stringify(wf);
        assert.doesNotMatch(text, /"(access_?token|refresh_?token|client_?secret|api_?key|password)"\s*:/i);
        assert.doesNotMatch(text, /\bBearer\s+[A-Za-z0-9._-]{10,}/);
        assert.doesNotMatch(text, /\bpat-[a-z0-9]{2,}-[0-9a-f-]{20,}/i, 'HubSpot private app token');
        assert.doesNotMatch(text, /sk-ant-/);
      });

      test('no real email address is committed (alerts use the __ALERT_TO__ placeholder)', () => {
        const addrs = JSON.stringify(wf).match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) ?? [];
        assert.deepEqual(addrs.filter((a) => !a.endsWith('.example')), []);
      });

      test('cross-workflow references resolve to a workflow in this repo', () => {
        for (const n of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.executeWorkflow')) {
          assert.ok(ids.has(n.parameters.workflowId.value), `${n.name} calls unknown workflow`);
        }
        if (wf.settings?.errorWorkflow) assert.ok(ids.has(wf.settings.errorWorkflow));
      });

      test('Google Sheets and HTTP calls target the one run-log sheet', () => {
        for (const n of wf.nodes) {
          const doc = n.parameters?.documentId?.value;
          if (doc) assert.equal(doc, SHEET_ID, n.name);
          const url = n.parameters?.url;
          if (url?.includes('sheets.googleapis.com')) assert.ok(url.includes(SHEET_ID), n.name);
        }
      });
    });
  }
});

describe('NEXT.md rule: writes are idempotent and never retried; reads retry', () => {
  const isWrite = (n) =>
    (n.type === 'n8n-nodes-base.googleSheets' && n.parameters.operation !== 'read') ||
    (n.type === 'n8n-nodes-base.gmail' && n.parameters.operation === 'send');
  const isRead = (n) =>
    (n.type === 'n8n-nodes-base.googleSheets' && n.parameters.operation === 'read') ||
    (n.type === 'n8n-nodes-base.gmail' && n.parameters.operation === 'getAll');

  for (const { file, wf } of all) {
    for (const n of wf.nodes) {
      if (isWrite(n)) {
        test(`${file}: write "${n.name}" has retryOnFail off`, () => assert.notEqual(n.retryOnFail, true));
      }
      if (isRead(n)) {
        test(`${file}: read "${n.name}" retries`, () => assert.equal(n.retryOnFail, true));
      }
    }
  }

  test('the run-log write is an upsert keyed on source_id, not a plain append', () => {
    const up = node(workflow('run-log-writer.json'), 'Upsert run');
    assert.equal(up.parameters.operation, 'appendOrUpdate');
    assert.deepEqual(up.parameters.columns.matchingColumns, ['source_id']);
  });
});

describe('run-log schema agrees everywhere', () => {
  test('init-headers writes exactly the columns the writer maps', () => {
    const body = JSON.parse(node(workflow('init-headers.json'), 'Headers: runs').parameters.jsonBody);
    assert.deepEqual(body.values[0], RUN_COLUMNS);
    const cols = node(workflow('run-log-writer.json'), 'Upsert run').parameters.columns;
    assert.deepEqual(Object.keys(cols.value), RUN_COLUMNS);
    assert.deepEqual(cols.schema.map((c) => c.id), RUN_COLUMNS);
  });

  const rowFields = (n) => n.parameters.assignments.assignments.map((a) => a.name);
  const expected = RUN_COLUMNS.filter((c) => c !== 'time'); // the writer stamps time itself
  for (const [file, name] of [
    ['intake-phase1.json', 'Shape log row'],
    ['intake-hubspot-phase1.json', 'Shape log row'],
    ['error-handler.json', 'Error row'],
  ]) {
    test(`${file} "${name}" sends every column the writer reads`, () => {
      assert.deepEqual(rowFields(node(workflow(file), name)), expected);
    });
  }

  test('the clear ranges in dev-reset keep row 1 (headers) and cover all 7 columns', () => {
    for (const n of workflow('dev-reset-log.json').nodes.filter((n) => n.parameters.url)) {
      assert.match(n.parameters.url, /\/values\/(runs|review)!A2:G:clear$/);
    }
  });
});

describe('spine wiring', () => {
  for (const file of ['intake-phase1.json', 'intake-hubspot-phase1.json']) {
    test(`${file}: scheduled intake routes failures to the error handler`, () => {
      const wf = workflow(file);
      assert.ok(wf.nodes.some((n) => n.type === 'n8n-nodes-base.scheduleTrigger'));
      assert.equal(wf.settings.errorWorkflow, 'n1ErrorHandler01');
    });

    test(`${file}: the run log is read once per poll, not once per item`, () => {
      assert.equal(node(workflow(file), 'Read run log').executeOnce, true);
      assert.equal(node(workflow(file), 'Read run log').alwaysOutputData, true, 'an empty log must not stop the run');
    });
  }

  test('Gmail intake filters by label NAME (label ids differ per account)', () => {
    const q = node(workflow('intake-phase1.json'), 'List labelled mail').parameters.filters.q;
    assert.equal(q, 'label:n1-lead');
  });

  test('the error handler logs even if the log write itself fails, and alerts only the placeholder', () => {
    const wf = workflow('error-handler.json');
    assert.equal(node(wf, 'Log the failure').onError, 'continueRegularOutput');
    assert.equal(node(wf, 'Alert owner').parameters.sendTo, '__ALERT_TO__');
    // Both IF branches converge on the log row: a throttled alert still logs.
    const branches = wf.connections['Send alert?'].main;
    assert.equal(branches[1][0].node, 'Error row');
    assert.equal(wf.connections['Alert owner'].main[0][0].node, 'Error row');
  });

  test('the error handler has no error workflow of its own (no alert loop)', () => {
    assert.equal(workflow('error-handler.json').settings.errorWorkflow, undefined);
  });

  test('import.sh publishes every workflow that is called or used as an error workflow', () => {
    const needed = new Set();
    for (const { wf } of all) {
      for (const n of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.executeWorkflow')) {
        needed.add(n.parameters.workflowId.value);
      }
      if (wf.settings?.errorWorkflow) needed.add(wf.settings.errorWorkflow);
    }
    const published = importScript.match(/for id in ([^;]+);/)[1].trim().split(/\s+/);
    assert.deepEqual([...needed].sort(), [...published].sort());
  });
});
