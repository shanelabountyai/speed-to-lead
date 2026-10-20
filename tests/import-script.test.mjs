// scripts/import.sh must refuse an ALERT_TO that would corrupt the sed substitution or the
// workflow JSON. Only rejection paths are exercised: they exit before n8n is ever invoked.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { ROOT } from './helpers.mjs';

const script = join(ROOT, 'scripts', 'import.sh');

test('import.sh parses', () => {
  assert.equal(spawnSync('bash', ['-n', script]).status, 0);
});

test('import.sh requires ALERT_TO', () => {
  const r = spawnSync('/bin/bash', [script], { env: {}, encoding: 'utf8' });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /ALERT_TO/);
});

for (const bad of ['not-an-address', 'a"b@example.com', 'a|b@example.com', 'a&b@example.com', 'a@b.com\\', 'a@b.com x@y.com']) {
  test(`import.sh rejects ALERT_TO=${JSON.stringify(bad)}`, () => {
    const r = spawnSync('/bin/bash', [script], { env: { ALERT_TO: bad }, encoding: 'utf8' });
    assert.equal(r.status, 1);
    assert.match(r.stderr, /not a plain email address/);
  });
}
