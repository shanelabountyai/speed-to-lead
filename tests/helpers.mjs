// Shared helpers for the offline checks. No dependencies: node:test + node:assert only.
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

export function loadWorkflows() {
  const dir = join(ROOT, 'workflows');
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .sort()
    .map((file) => ({ file, wf: JSON.parse(readFileSync(join(dir, file), 'utf8')) }));
}

export function workflow(file) {
  return JSON.parse(readFileSync(join(ROOT, 'workflows', file), 'utf8'));
}

export function node(wf, name) {
  const n = wf.nodes.find((x) => x.name === name);
  if (!n) throw new Error(`no node "${name}" in ${wf.name}`);
  return n;
}

export function loadFixtures() {
  return JSON.parse(readFileSync(join(ROOT, 'fixtures', 'n1-fixtures.json'), 'utf8'));
}

// Run an n8n Code node's jsCode (mode "run once for all items") outside n8n.
// `nodes` maps a node name to the list of item JSONs that node produced, which is what
// $('Name').all() / .first() read. `json` is $json, `staticData` backs $getWorkflowStaticData.
export function runCodeNode(codeNode, { nodes = {}, json = {}, staticData = {} } = {}) {
  const $ = (name) => {
    if (!(name in nodes)) throw new Error(`code node referenced unmocked node "${name}"`);
    const items = nodes[name].map((j) => ({ json: j }));
    return { all: () => items, first: () => items[0], item: items[0] };
  };
  const $getWorkflowStaticData = () => staticData;
  const fn = new Function('$', '$json', '$getWorkflowStaticData', codeNode.parameters.jsCode);
  return fn($, json, $getWorkflowStaticData).map((i) => i.json);
}

export const isTrigger = (n) => /trigger/i.test(n.type);
