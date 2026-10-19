// Pure scoring and routing. Rules arrive as data (the rule tables in rules/*.json, copied to sheet tabs);
// nothing here knows a threshold. Sheet cells come back as strings, so every comparison coerces.
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));

function fieldValue(field, lead, businessEmail) {
  return field === 'business_email' ? businessEmail : lead[field];
}

function matches(rule, value) {
  if (value === null || value === undefined) return false;
  const lo = num(rule.min), hi = num(rule.max);
  if (lo !== null || hi !== null) {
    const n = Number(value);
    return !Number.isNaN(n) && (lo === null || n >= lo) && (hi === null || n <= hi);
  }
  return String(rule.equals).split('|').includes(String(value));
}

function score(lead, rules, businessEmail) {
  const fired = rules.filter((r) => matches(r, fieldValue(r.field, lead, businessEmail)));
  return { score: fired.reduce((s, r) => s + Number(r.points), 0), rules_fired: fired.map((r) => r.rule) };
}

function band(total, bands) {
  return [...bands].sort((a, b) => Number(b.min_score) - Number(a.min_score)).find((b) => total >= Number(b.min_score));
}

// counts: how many leads were already routed per segment (from the run log), so round-robin survives restarts.
function route(size, routing, counts) {
  const n = num(size);
  const seg = routing.find((r) => (n === null ? r.min_size === '' && r.max_size === '' : (num(r.min_size) === null || n >= num(r.min_size)) && (num(r.max_size) === null || n <= num(r.max_size)) && !(r.min_size === '' && r.max_size === '')));
  const owners = seg.owners.split('|');
  return { segment: seg.segment, demo_owner: owners[(counts[seg.segment] || 0) % owners.length] };
}

module.exports = { score, band, route };
