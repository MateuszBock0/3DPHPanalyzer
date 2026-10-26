(function (root) {
  'use strict';

  function cellNumber(value) {
    if (value == null) return NaN;
    var s = String(value).trim().replace(/\u00a0/g, '').replace(/\s/g, '');
    if (!s) return NaN;
    if (s.includes(',') && s.includes('.')) {
      s = s.lastIndexOf(',') > s.lastIndexOf('.')
        ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    } else {
      s = s.replace(',', '.');
    }
    var n = Number(s);
    return Number.isFinite(n) ? n : NaN;
  }

  function parseLine(line, delimiter) {
    var result = [], current = '', quoted = false;
    for (var i = 0; i < line.length; i++) {
      var c = line[i];
      if (c === '"') {
        if (quoted && line[i + 1] === '"') { current += '"'; i++; }
        else quoted = !quoted;
      } else if (c === delimiter && !quoted) {
        result.push(current); current = '';
      } else current += c;
    }
    result.push(current);
    return result;
  }

  function delimiterOf(line) {
    var options = [',', ';', '\t'], best = ',', highest = -1;
    for (var j = 0; j < options.length; j++) {
      var count = parseLine(line, options[j]).length;
      if (count > highest) { best = options[j]; highest = count; }
    }
    return best;
  }

  function parseTime(value) {
    var s = String(value || '').trim();
    var match = s.match(/^(?:(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})\s+)?(\d{1,3}):(\d{2}):(\d{2})(?:[.,](\d+))?$/);
    if (match) {
      var sec = (+match[4]) * 3600 + (+match[5]) * 60 + (+match[6]) +
        (match[7] ? Number('0.' + match[7]) : 0);
      if (+match[5] >= 60 || +match[6] >= 60) return NaN;
      if (match[1]) {
        var year = +match[3]; year = year < 100 ? (year < 70 ? 2000 + year : 1900 + year) : year;
        var dt = Date.UTC(year, +match[2] - 1, +match[1]);
        return dt / 1000 + sec;
      }
      return sec;
    }
    if (/^\d+(?:[.,]\d+)?$/.test(s)) return cellNumber(s);
    var date = Date.parse(s);
    return Number.isFinite(date) ? date / 1000 : NaN;
  }

  function median(values) {
    if (!values.length) return NaN;
    var copy = values.slice().sort(function (a, b) { return a - b; });
    var k = Math.floor(copy.length / 2);
    return copy.length % 2 ? copy[k] : (copy[k - 1] + copy[k]) / 2;
  }

  function parseCSV(text) {
    if (typeof text !== 'string') throw new Error('Brak tekstu CSV.');
    var lines = text.replace(/^\uFEFF/, '').split(/\r\n|\n|\r/);
    var headerIndex = lines.findIndex(function (line) { return line.trim().length > 0; });
    if (headerIndex < 0) throw new Error('Plik jest pusty.');
    var delimiter = delimiterOf(lines[headerIndex]);
    var headers = parseLine(lines[headerIndex], delimiter).map(function (s) { return s.trim(); });
    var channels = [];
    headers.forEach(function (h, i) {
      if (i === 0) return;
      var m = h.match(/(?:kana[łl]|channel|ch)\s*[-:]?\s*(\d+)/i) || h.match(/^T\s*(\d+)\b/i);
      var id = m ? 'ch' + m[1] : 'ch' + i;
      channels.push({ id: id, label: h || id, index: i });
    });
    if (!channels.length) throw new Error('Nie znaleziono kolumn temperatur.');
    var rows = [], invalid = 0, base = NaN, prev = -Infinity, wrap = 0;
    for (var li = headerIndex + 1; li < lines.length; li++) {
      var raw = lines[li];
      if (!raw.trim()) continue;
      var parts = parseLine(raw, delimiter);
      var rawT = parseTime(parts[0]);
      if (!Number.isFinite(rawT)) { invalid++; continue; }
      if (Number.isFinite(prev) && rawT + wrap < prev - 43200) wrap += 86400;
      var absolute = rawT + wrap;
      if (Number.isFinite(prev) && absolute <= prev) { invalid++; continue; }
      var values = {}, usable = 0;
      channels.forEach(function (ch) {
        var v = cellNumber(parts[ch.index]);
        values[ch.id] = Number.isFinite(v) ? v : null;
        if (Number.isFinite(v)) usable++;
      });
      if (!usable) { invalid++; continue; }
      if (!Number.isFinite(base)) base = absolute;
      rows.push({ sec: absolute - base, temp: values });
      prev = absolute;
    }
    if (rows.length < 2) throw new Error('Brak co najmniej dwóch prawidłowych próbek temperatury.');
    var positive = [];
    for (var ri = 1; ri < Math.min(rows.length, 4001); ri++) {
      var diff = rows[ri].sec - rows[ri - 1].sec;
      if (diff > 0 && diff <= 60) positive.push(diff);
    }
    var interval = median(positive);
    if (!Number.isFinite(interval)) interval = 1;
    var gaps = [];
    for (var gi = 1; gi < rows.length; gi++) {
      var d = rows[gi].sec - rows[gi - 1].sec;
      if (d > Math.max(15, interval * 10)) {
        gaps.push({ from: rows[gi - 1].sec, to: rows[gi].sec, duration: d });
      }
    }
    return { channels: channels, rows: rows, gaps: gaps, invalid: invalid, step: interval,
      delimiter: delimiter, duration: rows[rows.length - 1].sec / 60 };
  }

  function average(values, keys) {
    var arr = keys.map(function (k) { return values[k]; }).filter(Number.isFinite);
    return arr.length ? arr.reduce(function (a, b) { return a + b; }, 0) / arr.length : null;
  }

  function compute(dataset, groups, intervals, reference) {
    var segments = [];
    for (var i = 0; i < intervals.length; i++) {
      var x = intervals[i], start = cellNumber(x.start), end = cellNumber(x.end), power = cellNumber(x.power);
      if (![start, end, power].every(Number.isFinite) || start < 0 || end <= start || power < 0)
        return { error: 'Nieprawidłowy etap Q: wymagane 0 ≤ od < do oraz Q ≥ 0.' };
      segments.push({ start: start, end: end, power: power });
    }
    segments.sort(function (a, b) { return a.start - b.start; });
    for (i = 1; i < segments.length; i++) {
      if (segments[i].start < segments[i - 1].end - 1e-8)
        return { error: 'Etapy Q nachodzą na siebie. Popraw przedziały czasowe.' };
    }
    if (!groups.e.length || !groups.c.length)
      return { error: 'Przypisz przynajmniej jedną termoparę do parownika i skraplacza.' };
    var all = dataset.rows.map(function (row) {
      var min = row.sec / 60, q = null;
      for (var si = 0; si < segments.length; si++) {
        if (min >= segments[si].start && min < segments[si].end) { q = segments[si].power; break; }
      }
      var te = average(row.temp, groups.e), tm = average(row.temp, groups.m), tc = average(row.temp, groups.c);
      var dt = te === null || tc === null ? null : te - tc;
      var r = dt !== null && q !== null && q > 0 ? dt / q : null;
      return { sec: row.sec, min: min, temp: row.temp, te: te, tm: tm, tc: tc, dt: dt, q: q, r: r, rr: null };
    });
    var refR = null, refPower = null, refError = '';
    if (reference && reference.enabled) {
      var a = cellNumber(reference.start), b = cellNumber(reference.end);
      if (!Number.isFinite(a) || !Number.isFinite(b) || a >= b) refError = 'Wybierz prawidłowe okno odniesienia.';
      else {
        var scope = all.filter(function (row) { return row.min >= a && row.min <= b && row.r !== null; });
        var qs = Array.from(new Set(scope.map(function (row) { return row.q; })));
        if (scope.length < 5 || qs.length !== 1) refError = 'Okno referencyjne wymaga ≥5 próbek i jednej stałej dodatniej mocy Q.';
        else {
          refR = median(scope.map(function (row) { return row.r; }));
          refPower = qs[0];
          if (!Number.isFinite(refR) || Math.abs(refR) < 1e-12) {
            refR = null; refError = 'Nie można obliczyć niezerowego R_ref.';
          } else {
            all.forEach(function (row) {
              if (row.r !== null && Math.abs(row.q - refPower) < 1e-9) row.rr = row.r / refR;
            });
          }
        }
      }
    }
    return { data: all, segments: segments, refR: refR, refPower: refPower, refError: refError };
  }

  root.PHPCore = {
    cellNumber: cellNumber, parseLine: parseLine, parseTime: parseTime,
    parseCSV: parseCSV, compute: compute, median: median
  };
})(typeof window !== 'undefined' ? window : globalThis);
