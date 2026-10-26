'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
require('../core.js');
const core = globalThis.PHPCore;

function fixture() {
  return [
    '"","Kanał 1 Ostatni (C)","Kanał 3 Ostatni (C)","Kanał 4 Ostatni (C)","Kanał 5 Ostatni (C)","Kanał 6 Ostatni (C)","Kanał 7 Ostatni (C)"',
    '"00:00:00","30,0","32,0","26,0","26,0","20,0","22,0"',
    '"00:00:01","31,0","33,0","26,0","26,0","20,0","22,0"',
    '"00:00:02","32,0","34,0","26,0","26,0","20,0","22,0"',
    '"00:00:03","33,0","35,0","26,0","26,0","20,0","22,0"',
    '"00:00:04","34,0","36,0","26,0","26,0","20,0","22,0"',
    '"00:01:00","35,0","37,0","26,0","26,0","20,0","22,0"',
    '"00:01:01","36,0","38,0","26,0","26,0","20,0","22,0"'
  ].join('\n');
}
const groups = { e: ['ch1','ch3'], m: ['ch4','ch5'], c: ['ch6','ch7'] };

test('PicoLog decimal comma and channel names', () => {
  const parsed = core.parseCSV(fixture());
  assert.deepEqual(parsed.channels.map(c => c.id), ['ch1','ch3','ch4','ch5','ch6','ch7']);
  assert.equal(parsed.rows.length, 7);
  assert.equal(parsed.rows[0].temp.ch1, 30);
  assert.equal(parsed.rows[0].temp.ch3, 32);
  assert.equal(parsed.step, 1);
});
test('missing time is a real recording gap, not a fabricated connecting interval', () => {
  const parsed = core.parseCSV(fixture());
  assert.equal(parsed.gaps.length, 1);
  assert.equal(parsed.gaps[0].from, 4);
  assert.equal(parsed.gaps[0].to, 60);
});
test('invalid and empty rows are discarded, never interpolated', () => {
  const csv = fixture() + '\n"00:01:02","","","","","",""\n"bad","33","33","33","33","33","33"\n';
  const parsed = core.parseCSV(csv);
  assert.equal(parsed.rows.length, 7);
  assert.equal(parsed.invalid, 2);
});
test('Q is unknown unless supplied; 0W cannot produce R', () => {
  const parsed = core.parseCSV(fixture());
  const a = core.compute(parsed, groups, [], {enabled:false});
  assert.equal(a.data[0].dt, 10);
  assert.equal(a.data[0].r, null);
  assert.equal(a.data[0].q, null);
  const b = core.compute(parsed, groups, [
    {start:0,end:0.04,power:10},
    {start:0.04,end:0.08,power:0}
  ], {enabled:false});
  assert.equal(b.data[0].q, 10);
  assert.equal(b.data[0].r, 1);
  assert.equal(b.data[4].q, 0);
  assert.equal(b.data[4].r, null);
  assert.equal(b.data[5].q, null);
});
test('overlapping stages rejected; no silent power assumption', () => {
  const parsed = core.parseCSV(fixture());
  const result = core.compute(parsed, groups, [
    {start:0,end:2,power:5},
    {start:1,end:3,power:10}
  ], {enabled:false});
  assert.match(result.error, /nachodzą/);
});
test('reference ratio only at same Q as the reference interval', () => {
  const parsed = core.parseCSV(fixture());
  const result = core.compute(parsed, groups, [
    {start:0,end:0.09,power:10},
    {start:0.09,end:2,power:20}
  ], {enabled:true,start:0,end:0.08});
  assert.equal(result.refPower, 10);
  assert.ok(Number.isFinite(result.refR));
  assert.ok(Number.isFinite(result.data[1].rr));
  assert.equal(result.data[5].rr, null);
});
test('date and midnight handling', () => {
  const txt = '"Time";"ch1";"ch6"\n"23:59:58";"30";"20"\n"23:59:59";"32";"20"\n"00:00:00";"35";"21"';
  const parsed = core.parseCSV(txt);
  assert.deepEqual(parsed.rows.map(r => r.sec), [0,1,2]);
});
test('missing source file rejected clearly', () => {
  assert.throws(() => core.parseCSV(''), /pusty/);
});
