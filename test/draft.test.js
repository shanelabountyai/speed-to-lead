const test = require('node:test');
const assert = require('node:assert');
const D = require('../lib/draft');
const L = require('../lib/lead');
const rd = (n) => require(`../rules/${n}.json`);
const fx = require('../fixtures/n1-fixtures.json');
const tables = { config: rd('config'), score_rules: rd('score_rules'), bands: rd('bands'), routing: rd('routing'), rates: rd('rates') };
const cfg = D.cfgOf(tables);

// Planted-fabrication gate (as in Use-Case Studio): every planted claim must be rejected AND named, and the clean
// controls must pass. A checker that rejects everything fails the controls; one that passes everything fails the plants.
const CLEAN = [
  'Duplicate contacts and wrong lifecycle stages make every campaign harder to trust, so it makes sense to fix the data first.',
  'It sounds like the partners want a single view of proposals and wins that they do not have to assemble by hand.',
  'Records split across properties make it hard to see one guest or account clearly.',
  // Real false rejects from the first live run (2026-10-23): the lead's own goal and metric, not a firm claim.
  "You're managing multiple locations and want to get your HubSpot workflows operational so you can start automating patient communications.",
  "You're looking to consolidate your proposal, win rate, and revenue data from HubSpot into a single view for your partners to track performance by project type.",
];
const PLANTS = [
  ['digit', 'Teams of 40 often hit exactly this problem.'],
  ['date or time', 'A cleanup like yours usually takes 3 weeks.'],
  ['digit', 'Your 220-person team deserves a clean CRM.'],
  ['number word', 'Two of our recent clients had the same problem.'],
  ['money', 'Projects like this typically come in around $6,000.'],
  ['money', 'Our pricing for dashboard work is flat and simple.'],
  ['money', 'That budget is a good fit for this kind of work.'],
  ['date or time', 'Having it live before your board meeting next week makes sense.'],
  ['date or time', 'Let us talk on Thursday about the duplicates.'],
  ['date or time', 'A dashboard ready by Q4 would help the partners.'],
  ['commitment', 'We will have your HubSpot cleaned up before the campaign launches.'],
  ['commitment', 'We can deliver the dashboard before the meeting.'],
  ['commitment', 'We guarantee the duplicates will be gone.'],
  ['commitment', "I'll make sure the board sees it."],
  ['commitment', 'Our team could have this running for you.'],
  ['money', 'Our rates are competitive for this kind of work.'],
];

test('fabrication gate: every plant rejected and named, every clean control passes', () => {
  for (const s of CLEAN) assert.deepStrictEqual(D.checkAck(s).ok, true, `control rejected: ${s} (${D.checkAck(s).reason})`);
  for (const [kind, s] of PLANTS) {
    const r = D.checkAck(s);
    assert.strictEqual(r.ok, false, `plant passed: ${s}`);
    assert.ok(r.reason.startsWith(kind), `plant "${s}" rejected as "${r.reason}", expected ${kind}`);
  }
});

test('checkAck: shape rules', () => {
  assert.strictEqual(D.checkAck('').ok, false);
  assert.strictEqual(D.checkAck('See https://evil.example for more.').ok, false);
  assert.strictEqual(D.checkAck('One. Two. Three sentences here.').ok, false);
  assert.strictEqual(D.checkAck('"Messy data makes reporting hard."').text, 'Messy data makes reporting hard.');
});

test('fillTemplate: names, need phrase, ack, owner; template-only when ack is empty; reply subject', () => {
  const [d] = L.decideBatch([{ msg: { source: 'gmail', source_id: 'x', from_email: 'dana@north.example', subject: 'CRM cleanup' }, ex: fx.fixtures[0].labels }], tables, []);
  const a = D.fillTemplate(d, 'Messy data makes reporting hard.', cfg);
  assert.strictEqual(a.subject, 'Re: CRM cleanup');
  assert.match(a.body, /^Hi Dana,\n\nThanks for getting in touch about cleaning up your CRM\. Messy data makes reporting hard\.\n\n/);
  assert.match(a.body, /\nJordan\nTallgrass Advisory$/);
  const b = D.fillTemplate({ ...d, ex: { ...d.ex, name: null, need: 'other' }, subject: '' }, '', cfg);
  assert.strictEqual(b.subject, 'Your enquiry to Tallgrass Advisory');
  assert.match(b.body, /^Hi there,\n\nThanks for getting in touch about what you are looking for\.\n\nThe best/);
});

test('the template itself carries no price, date or number', () => {
  const t = cfg.reply_template.replace(/\{\w+\}/g, '');
  assert.ok(!/\d|[$€£]/.test(t), t);
});

test('dueAt: today, next business day over a weekend, offset kept', () => {
  assert.strictEqual(D.dueAt('today', '2026-10-23T09:15:00.000-04:00'), '2026-10-23T17:00:00-04:00');
  assert.strictEqual(D.dueAt('next_business_day', '2026-10-23T09:15:00.000-04:00'), '2026-10-26T17:00:00-04:00'); // Fri -> Mon
  assert.strictEqual(D.dueAt('next_business_day', '2026-10-21T09:15:00.000+00:00'), '2026-10-22T17:00:00+00:00');
  assert.throws(() => D.dueAt('', '2026-10-21T09:15:00.000Z'));
});

test('mimeRaw: decodes to a threaded reply with the body intact', () => {
  const raw = D.mimeRaw({ to: 'a@b.example.com', subject: 'Re: Café', body: 'Hi\n\nThanks — ok', inReplyTo: '<m1@x>' });
  const txt = Buffer.from(raw, 'base64url').toString();
  assert.match(txt, /^To: a@b\.example\.com\r\nSubject: =\?UTF-8\?B\?/);
  assert.match(txt, /In-Reply-To: <m1@x>\r\nReferences: <m1@x>/);
  assert.strictEqual(Buffer.from(txt.split('\r\n\r\n')[1], 'base64').toString(), 'Hi\n\nThanks — ok');
});

test('approvalState: pending, sent after the draft, discarded', () => {
  assert.strictEqual(D.approvalState(true, [], 0), 'pending');
  assert.strictEqual(D.approvalState(false, [{ labelIds: ['INBOX'], internalDate: '1000' }, { labelIds: ['SENT'], internalDate: '500000' }], 400000), 'sent');
  assert.strictEqual(D.approvalState(false, [{ labelIds: ['INBOX'], internalDate: '1000' }], 400000), 'discarded');
});
