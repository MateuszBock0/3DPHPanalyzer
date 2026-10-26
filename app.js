(function () {
  'use strict';
  var core = window.PHPCore;
  var byId = function (id) { return document.getElementById(id); };
  var files = [], current = 0, plots = [];
  var colors = { e: '#d84b36', m: '#a1814c', c: '#2588b8' };
  var escapeCsv = function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
  function filename(name) { return name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]+/g, '_'); }
  function fmt(x, precision) { return x == null || !Number.isFinite(x) ? '—' : Number(x).toFixed(precision == null ? 2 : precision); }
  function msg(text, error) {
    var n = byId('notice'); n.textContent = text;
    n.classList.remove('hidden'); n.classList.toggle('error', !!error);
  }
  function selection(el) { return Array.from(el.selectedOptions).map(function (o) { return o.value; }); }
  function currentFile() { return files[current]; }
  function setting() { return currentFile().settings; }

  async function fileContent(file) {
    var bytes = new Uint8Array(await file.arrayBuffer());
    if (bytes[0] === 255 && bytes[1] === 254) return new TextDecoder('utf-16le').decode(bytes.subarray(2));
    if (bytes[0] === 254 && bytes[1] === 255) return new TextDecoder('utf-16be').decode(bytes.subarray(2));
    var decoded = new TextDecoder('utf-8').decode(bytes);
    if ((decoded.match(/\uFFFD/g) || []).length > 8) {
      try { return new TextDecoder('windows-1250').decode(bytes); } catch (_) {}
    }
    return decoded;
  }

  function defaults(parsed) {
    var ids = parsed.channels.map(function (c) { return c.id; });
    var e = ['ch1', 'ch3'].filter(function (x) { return ids.includes(x); });
    var m = ['ch4', 'ch5'].filter(function (x) { return ids.includes(x); });
    var c = ['ch6', 'ch7'].filter(function (x) { return ids.includes(x); });
    if (!e.length) e = ids.slice(0, Math.min(2, ids.length));
    if (!c.length) c = ids.filter(function (x) { return !e.includes(x); }).slice(-2);
    return { groups: { e: e, m: m, c: c }, stages: [], reference: { enabled: false, start: '0', end: '10' },
      zoomFrom: 0, zoomTo: parsed.duration, mode: 'r' };
  }

  async function receiveFiles(fileList) {
    var incoming = Array.from(fileList).filter(function (f) { return /\.(csv|txt)$/i.test(f.name); });
    if (!incoming.length) return msg('Wybierz pliki CSV lub TXT.', true);
    var good = 0, failures = [];
    for (var i = 0; i < incoming.length; i++) {
      var f = incoming[i], key = f.name + ':' + f.size + ':' + f.lastModified;
      if (files.some(function (x) { return x.key === key; })) continue;
      try {
        var parsed = core.parseCSV(await fileContent(f));
        files.push({ name: f.name, key: key, parsed: parsed, settings: defaults(parsed), computed: null });
        good++;
      } catch (e) { failures.push(f.name + ': ' + e.message); }
    }
    if (files.length) {
      current = files.length - 1;
      byId('workspace').classList.remove('hidden');
      renderFileSelector(); selectFile();
    }
    if (failures.length) msg('Wczytano: ' + good + '. Błędy: ' + failures.join(' | '), true);
    else if (good) msg('Wczytano ' + good + ' plik(i). Q pozostaje nieznane, dopóki go nie wprowadzisz.');
  }

  function renderFileSelector() {
    var select = byId('datasetSelect');
    select.textContent = '';
    files.forEach(function (f, i) {
      var option = document.createElement('option');
      option.value = String(i); option.textContent = f.name; select.appendChild(option);
    });
    select.value = String(current);
  }
  function renderMapping() {
    var f = currentFile();
    [['evapChannels', 'e'], ['midChannels', 'm'], ['condChannels', 'c']].forEach(function (entry) {
      var select = byId(entry[0]);
      select.textContent = '';
      f.parsed.channels.forEach(function (ch) {
        var opt = document.createElement('option');
        opt.value = ch.id; opt.textContent = ch.label;
        opt.selected = f.settings.groups[entry[1]].includes(ch.id);
        select.appendChild(opt);
      });
    });
  }

  function powerInput(value, row, field, name) {
    var input = document.createElement('input');
    input.type = 'number'; input.step = 'any'; input.min = '0'; input.value = value;
    input.setAttribute('aria-label', name);
    input.addEventListener('input', function () {
      row[field] = input.value;
      renderAnalysis();
    });
    return input;
  }

  function renderPowerRows() {
    var body = byId('powerRows'); body.textContent = '';
    var stages = setting().stages;
    if (!stages.length) {
      var tr = document.createElement('tr'), td = document.createElement('td');
      td.colSpan = 4; td.className = 'hint'; td.textContent = 'Nie podano mocy. Dodaj etap, aby wyznaczyć R_app.';
      tr.appendChild(td); body.appendChild(tr);
    }
    stages.forEach(function (st, index) {
      var tr = document.createElement('tr');
      [['start','Od [min]'],['end','Do [min]'],['power','Moc Q [W]']].forEach(function (c) {
        var td = document.createElement('td');
        td.appendChild(powerInput(st[c[0]], st, c[0], c[1] + ' — etap ' + (index + 1)));
        tr.appendChild(td);
      });
      var td = document.createElement('td'), del = document.createElement('button');
      del.textContent = '×'; del.title = 'Usuń etap'; del.setAttribute('aria-label', 'Usuń etap ' + (index + 1));
      del.addEventListener('click', function () { stages.splice(index, 1); renderPowerRows(); renderAnalysis(); });
      td.appendChild(del); tr.appendChild(td); body.appendChild(tr);
    });
  }
  function selectFile() {
    if (!files.length) return;
    renderMapping();
    renderPowerRows();
    var s = setting();
    byId('enableRef').checked = s.reference.enabled;
    byId('refFrom').value = s.reference.start;
    byId('refTo').value = s.reference.end;
    byId('zoomFrom').value = fmt(s.zoomFrom, 3);
    byId('zoomTo').value = fmt(s.zoomTo, 3);
    byId('resistanceMode').value = s.mode;
    renderAnalysis();
  }

  function zoom() {
    var s = setting(), from = core.cellNumber(s.zoomFrom), to = core.cellNumber(s.zoomTo);
    if (!Number.isFinite(from) || !Number.isFinite(to) || from < 0 || from >= to) {
      byId('zoomStatus').textContent = 'Nieprawidłowy zakres — pokazano cały pomiar.';
      return [0, currentFile().parsed.duration];
    }
    byId('zoomStatus').textContent = fmt(to - from, 2) + ' min wybranego przebiegu';
    return [from, to];
  }

  function renderAnalysis() {
    if (!files.length) return;
    var f = currentFile(), parsed = f.parsed, s = f.settings;
    var seen = s.groups.e.concat(s.groups.m, s.groups.c);
    var duplicate = seen.length !== new Set(seen).size;
    var results = core.compute(parsed, s.groups, s.stages, s.reference);
    var error = duplicate ? 'Nie przypisuj tej samej termopary do więcej niż jednej strefy.' : (results.error || '');
    if (error) {
      byId('powerWarning').textContent = error + ' Do czasu poprawy Q pozostaje nieznane.';
      results = core.compute(parsed, s.groups, [], { enabled: false });
      if (results.error) {
        byId('powerWarning').textContent = results.error;
        return;
      }
    } else {
      byId('powerWarning').textContent = s.stages.length
        ? 'Q jest wpisane ręcznie. Poza zdefiniowanymi etapami moc pozostaje nieznana.'
        : 'Bez wpisanej mocy pokazywane są temperatury i ΔT; R [K/W] pozostaje niedostępne.';
    }
    f.computed = results;
    byId('refStatus').textContent = results.refError || (results.refR !== null
      ? 'R_ref = ' + fmt(results.refR, 4) + ' K/W przy Q = ' + fmt(results.refPower, 2) + ' W. R/R_ref pokazujemy tylko przy tej samej Q.'
      : 'R/R_ref wymaga ręcznie wybranego okna przy jednej stałej dodatniej Q.');
    byId('dataSummary').textContent = parsed.rows.length.toLocaleString('pl-PL') + ' próbek · ' +
      fmt(parsed.duration, 2) + ' min · krok typowy ' + fmt(parsed.step, 2) + ' s · ' +
      parsed.invalid + ' pominiętych wierszy · ' + parsed.gaps.length + ' luk rejestracji';
    var scope = zoom(), subset = results.data.filter(function (r) { return r.min >= scope[0] && r.min <= scope[1]; });
    if (!subset.length) { scope = [0, parsed.duration]; subset = results.data; }
    var maxTe = Math.max.apply(null, subset.map(function (r) { return r.te == null ? -Infinity : r.te; }));
    var avgDelta = core.median(subset.map(function (r) { return r.dt; }).filter(Number.isFinite));
    var avgR = core.median(subset.map(function (r) { return r.r; }).filter(Number.isFinite));
    var knownQ = subset.filter(function (r) { return r.q !== null; }).length;
    var metrics = [
      ['Maks. Te', fmt(maxTe, 2) + ' °C', 'w bieżącym zakresie'],
      ['Mediana ΔT', fmt(avgDelta, 2) + ' K', 'w bieżącym zakresie'],
      ['Mediana R_app', fmt(avgR, 3) + ' K/W', 'tylko dla Q > 0'],
      ['Przypisana Q', fmt(knownQ / subset.length * 100, 1) + '%', 'pokrycie próbek mocą']
    ];
    var target = byId('metrics'); target.textContent = '';
    metrics.forEach(function (m) {
      var div = document.createElement('div'); div.className = 'metric';
      var lab = document.createElement('label'), num = document.createElement('strong'), small = document.createElement('small');
      lab.textContent = m[0]; num.textContent = m[1]; small.textContent = m[2];
      div.appendChild(lab); div.appendChild(num); div.appendChild(small); target.appendChild(div);
    });

    var curves = [], groupNames = [['e', 'te'], ['m', 'tm'], ['c', 'tc']];
    groupNames.forEach(function (g) {
      s.groups[g[0]].forEach(function (id) {
        curves.push({ name: id, color: colors[g[0]], width: 1, opacity: .22, get: function (r) { return r.temp[id]; } });
      });
    });
    groupNames.forEach(function (g) {
      if (s.groups[g[0]].length) curves.push({ name: g[1], color: colors[g[0]], width: 2.8, opacity: 1, get: function (r) { return r[g[1]]; } });
    });
    plots = [
      chart(subset, curves, scope, 'Temperatura [°C]', parsed.gaps, parsed.step),
      chart(subset, [{ color: '#09927c', width: 2.8, get: function (r) { return r.dt; } }], scope, 'ΔT [K]', parsed.gaps, parsed.step),
      chart(subset, [{ color: '#ad693e', width: 2.8, get: function (r) { return r.q; }, step: true }], scope, 'Q [W]', parsed.gaps, parsed.step),
      chart(subset, [{ color: '#8850b8', width: 2.8, get: function (r) { return s.mode === 'rr' ? r.rr : r.r; } }], scope,
        s.mode === 'rr' ? 'R/R_ref [−]' : 'R_app [K/W]', parsed.gaps, parsed.step, s.mode === 'rr' ? 1 : null)
    ];
    plots.forEach(function (svg, i) { byId('plot' + i).innerHTML = svg; });
  }

  function chart(data, lines, limits, ylabel, gaps, nominal, referenceLine) {
    var W = 1120, H = 298, L = 76, T = 15, R = 20, B = 42, plotW = W - L - R, plotH = H - T - B;
    var x0 = limits[0], x1 = limits[1], xspan = Math.max(1e-7, x1 - x0);
    var val = [];
    lines.forEach(function (line) { data.forEach(function (r) {
      var y = line.get(r); if (y != null && Number.isFinite(y)) val.push(y);
    }); });
    if (referenceLine !== null && referenceLine !== undefined) val.push(referenceLine);
    var min = val.length ? Math.min.apply(null, val.slice(0, 10000)) : 0;
    var max = val.length ? Math.max.apply(null, val.slice(0, 10000)) : 1;
    for (var vi = 10000; vi < val.length; vi++) {
      min = Math.min(min, val[vi]); max = Math.max(max, val[vi]);
    }
    if (ylabel === 'Q [W]') min = Math.min(0, min);
    if (max === min) { min -= .5; max += .5; }
    var margin = (max - min) * .075; min -= margin; max += margin;
    function xp(sec) { return L + (sec / 60 - x0) / xspan * plotW; }
    function yp(v) { return T + (max - v) / (max - min) * plotH; }
    function num(x) { return Number(x).toFixed(2); }
    var out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H +
      '" role="img" aria-label="' + ylabel + ' w funkcji czasu">',
      '<rect width="' + W + '" height="' + H + '" fill="#fff"/>'];
    for (var t = 0; t <= 5; t++) {
      var p = t / 5, yy = T + plotH * p, xx = L + plotW * p;
      out.push('<line x1="' + L + '" x2="' + (L + plotW) + '" y1="' + num(yy) + '" y2="' + num(yy) + '" stroke="#e9eef3"/>');
      out.push('<line x1="' + num(xx) + '" x2="' + num(xx) + '" y1="' + T + '" y2="' + (T + plotH) + '" stroke="#edf1f5"/>');
      out.push('<text x="' + (L - 10) + '" y="' + num(yy + 4) + '" text-anchor="end" fill="#6b7f90" font-size="12">' + num(max - p * (max - min)) + '</text>');
      out.push('<text x="' + num(xx) + '" y="' + (H - 23) + '" text-anchor="middle" fill="#6b7f90" font-size="12">' + num(x0 + p * xspan) + '</text>');
    }
    out.push('<defs><clipPath id="clipgraph"><rect x="' + L + '" y="' + T + '" width="' + plotW + '" height="' + plotH + '"/></clipPath></defs>');
    out.push('<g clip-path="url(#clipgraph)">');
    gaps.forEach(function (g) {
      var a = Math.max(x0, g.from / 60), b = Math.min(x1, g.to / 60);
      if (b > a) out.push('<rect x="' + num(xp(a * 60)) + '" y="' + T + '" width="' +
        num((b - a) / xspan * plotW) + '" height="' + plotH + '" fill="#d0d8de" opacity=".42"/>');
    });
    if (referenceLine !== null && referenceLine !== undefined) {
      out.push('<line x1="' + L + '" y1="' + num(yp(referenceLine)) + '" x2="' + (L + plotW) +
        '" y2="' + num(yp(referenceLine)) + '" stroke="#8199ab" stroke-dasharray="6 4"/>');
    }
    var maxpoints = 2600, stride = Math.max(1, Math.ceil(data.length / maxpoints));
    lines.forEach(function (line) {
      var path = '', prev = null;
      for (var i = 0; i < data.length; i += stride) {
        var end = Math.min(data.length, i + stride), points = [i, end - 1], low = Infinity, high = -Infinity, lo = -1, hi = -1;
        for (var j = i; j < end; j++) {
          var v = line.get(data[j]);
          if (v == null || !Number.isFinite(v)) continue;
          if (v < low) { low = v; lo = j; }
          if (v > high) { high = v; hi = j; }
        }
        if (lo >= 0) points.push(lo);
        if (hi >= 0) points.push(hi);
        points = Array.from(new Set(points)).sort(function (a, b) { return a - b; });
        points.forEach(function (at) {
          var row = data[at], y = line.get(row);
          if (y == null || !Number.isFinite(y)) { prev = null; return; }
          var broken = !prev || (row.sec - prev.sec > Math.max(15, nominal * 10, stride * nominal * 3));
          if (!broken) {
            broken = gaps.some(function (g) { return g.from >= prev.sec && g.to <= row.sec; });
          }
          path += (broken ? 'M' : line.step ? 'H' : 'L') + num(xp(row.sec)) +
            (broken ? ' ' + num(yp(y)) : line.step ? '' : ' ' + num(yp(y)));
          if (!broken && line.step && prev.y !== y) {
            // Horizontal to the new X, then vertical at the same X.
            path += 'V' + num(yp(y));
          }
          prev = { sec: row.sec, y: y };
        });
      }
      if (path) out.push('<path d="' + path + '" fill="none" stroke="' + line.color +
        '" stroke-opacity="' + (line.opacity == null ? 1 : line.opacity) + '" stroke-width="' +
        line.width + '" stroke-linejoin="round" stroke-linecap="round"/>');
    });
    out.push('</g>');
    if (!val.length) out.push('<text x="' + (L + plotW / 2) + '" y="' + (T + plotH / 2) +
      '" text-anchor="middle" font-size="16" fill="#7b90a0">Brak danych dla tego parametru</text>');
    out.push('<text x="' + (L + plotW / 2) + '" y="' + (H - 3) +
      '" text-anchor="middle" font-size="13" fill="#4c6275">Czas od początku CSV [min]</text>');
    out.push('<text x="' + L + '" y="11" fill="#567082" font-size="13">' + ylabel + '</text>');
    out.push('</svg>');
    return out.join('');
  }

  function derivedCSV() {
    var f = currentFile(), head = ['t_s', 't_min'];
    f.parsed.channels.forEach(function (ch) { head.push(ch.id + '_C'); });
    head.push('Te_C', 'Tm_C', 'Tc_C', 'DeltaT_K', 'Q_W', 'R_app_K_W', 'R_relative');
    var arr = [head.map(escapeCsv).join(';')];
    f.computed.data.forEach(function (r) {
      var row = [r.sec, r.min];
      f.parsed.channels.forEach(function (ch) { row.push(r.temp[ch.id]); });
      row.push(r.te, r.tm, r.tc, r.dt, r.q, r.r, r.rr);
      arr.push(row.map(function (value) { return value == null || !Number.isFinite(value) ? '' : Number(value).toFixed(6); }).join(';'));
    });
    return '\uFEFF' + arr.join('\r\n') + '\r\n';
  }

  function save(name, blob) {
    var url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = name; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 5000);
  }
  function exportChart(index, format) {
    if (!plots[index]) return;
    var name = filename(currentFile().name) + '_' + ['temperatury', 'deltaT', 'moc_Q', 'opor'][index];
    var blob = new Blob([plots[index]], { type: 'image/svg+xml;charset=utf-8' });
    if (format === 'svg') return save(name + '.svg', blob);
    var u = URL.createObjectURL(blob), image = new Image();
    image.onload = function () {
      var canvas = document.createElement('canvas'); canvas.width = 2240; canvas.height = 596;
      var c = canvas.getContext('2d'); c.fillStyle = '#fff'; c.fillRect(0, 0, canvas.width, canvas.height);
      c.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (out) { if (out) save(name + '.png', out); URL.revokeObjectURL(u); }, 'image/png');
    };
    image.onerror = function () { msg('Nie udało się przygotować PNG. Spróbuj eksportu SVG.', true); URL.revokeObjectURL(u); };
    image.src = u;
  }

  function little(arr, number, bytes) { for (var j = 0; j < bytes; j++) arr.push((number >>> (j * 8)) & 255); }
  var crcTable = Array.from({ length: 256 }, function (_, i) {
    var c = i;
    for (var k = 0; k < 8; k++) c = c & 1 ? (0xEDB88320 ^ (c >>> 1)) : c >>> 1;
    return c >>> 0;
  });
  function crc32(arr) {
    var v = 0xFFFFFFFF;
    for (var i = 0; i < arr.length; i++) v = crcTable[(v ^ arr[i]) & 255] ^ (v >>> 8);
    return (v ^ 0xFFFFFFFF) >>> 0;
  }
  function zip(entries) {
    var encoder = new TextEncoder(), local = [], central = [], offset = 0;
    entries.forEach(function (item) {
      var name = encoder.encode(item.name), bytes = item.bytes instanceof Uint8Array ? item.bytes : encoder.encode(item.text);
      var crc = crc32(bytes), header = [];
      little(header, 0x04034b50, 4); little(header, 20, 2); little(header, 0x800, 2);
      little(header, 0, 2); little(header, 0, 2); little(header, 0, 2);
      little(header, crc, 4); little(header, bytes.length, 4); little(header, bytes.length, 4);
      little(header, name.length, 2); little(header, 0, 2);
      local.push(new Uint8Array(header), name, bytes);
      var ch = [];
      little(ch, 0x02014b50, 4); little(ch, 20, 2); little(ch, 20, 2);
      little(ch, 0x800, 2); little(ch, 0, 2); little(ch, 0, 2); little(ch, 0, 2);
      little(ch, crc, 4); little(ch, bytes.length, 4); little(ch, bytes.length, 4);
      little(ch, name.length, 2); little(ch, 0, 2); little(ch, 0, 2);
      little(ch, 0, 2); little(ch, 0, 2); little(ch, 0, 4); little(ch, offset, 4);
      central.push(new Uint8Array(ch), name);
      offset += header.length + name.length + bytes.length;
    });
    var centralSize = central.reduce(function (sum, a) { return sum + a.length; }, 0), tail = [];
    little(tail, 0x06054b50, 4); little(tail, 0, 2); little(tail, 0, 2);
    little(tail, entries.length, 2); little(tail, entries.length, 2);
    little(tail, centralSize, 4); little(tail, offset, 4); little(tail, 0, 2);
    return new Blob(local.concat(central, [new Uint8Array(tail)]), { type: 'application/zip' });
  }
  function exportReport() {
    var f = currentFile(), base = filename(f.name);
    var list = [
      { name: base + '_przebiegi.csv', text: derivedCSV() },
      { name: 'konfiguracja.json', text: JSON.stringify({
        source: f.name, channels: f.settings.groups, Q_intervals_min_W: f.settings.stages,
        reference_min: f.settings.reference, gaps_s: f.parsed.gaps,
        note: 'R_app=(Te-Tc)/Q. Approximate, electrical input power, not verified transported heat.'
      }, null, 2) },
      { name: 'PRZECZYTAJ.txt', text: '3D PHP Analyzer — raport offline\n' +
        'Oryginalny CSV nie jest modyfikowany.\n' +
        'Q pochodzi tylko z harmonogramu użytkownika. Brak Q i Q=0 nie dają wartości R_app.\n' +
        'R_app=(Te-Tc)/Q [K/W] jest pozornym oporem cieplnym.\n' +
        'R/R_ref jest obliczany tylko przy mocy identycznej z oknem odniesienia.\n' +
        'Szare pasma na wykresach oznaczają brak rejestracji. Oscylacje termiczne nie są dowodem przepływu czynnika.\n' }
    ];
    plots.forEach(function (svg, i) {
      list.push({ name: 'wykresy/' + ['temperatury', 'deltaT', 'moc_Q', 'opor'][i] + '.svg', text: svg });
    });
    save(base + '_raport.zip', zip(list));
  }

  byId('pickButton').addEventListener('click', function () { byId('files').click(); });
  byId('files').addEventListener('change', function (e) { receiveFiles(e.target.files); e.target.value = ''; });
  var zone = byId('dropzone');
  ['dragenter', 'dragover'].forEach(function (name) { zone.addEventListener(name, function (e) { e.preventDefault(); zone.classList.add('dragover'); }); });
  ['dragleave', 'drop'].forEach(function (name) { zone.addEventListener(name, function (e) { e.preventDefault(); zone.classList.remove('dragover'); }); });
  zone.addEventListener('drop', function (e) { receiveFiles(e.dataTransfer.files); });
  byId('datasetSelect').addEventListener('change', function (e) { current = Number(e.target.value); selectFile(); });
  [['evapChannels', 'e'], ['midChannels', 'm'], ['condChannels', 'c']].forEach(function (m) {
    byId(m[0]).addEventListener('change', function (e) { setting().groups[m[1]] = selection(e.target); renderAnalysis(); });
  });
  byId('addStage').addEventListener('click', function () {
    var stages = setting().stages, previous = stages[stages.length - 1], begin = previous ? previous.end : '0';
    setting().stages.push({ start: begin, end: fmt(currentFile().parsed.duration, 3), power: '' });
    renderPowerRows(); renderAnalysis();
  });
  byId('enableRef').addEventListener('change', function (e) { setting().reference.enabled = e.target.checked; renderAnalysis(); });
  [['refFrom','start'],['refTo','end']].forEach(function (x) {
    byId(x[0]).addEventListener('input', function (e) { setting().reference[x[1]] = e.target.value; renderAnalysis(); });
  });
  [['zoomFrom','zoomFrom'],['zoomTo','zoomTo']].forEach(function (x) {
    byId(x[0]).addEventListener('change', function (e) { setting()[x[1]] = e.target.value; renderAnalysis(); });
  });
  byId('resetZoom').addEventListener('click', function () {
    setting().zoomFrom = 0; setting().zoomTo = currentFile().parsed.duration;
    byId('zoomFrom').value = 0; byId('zoomTo').value = fmt(setting().zoomTo, 3); renderAnalysis();
  });
  byId('resistanceMode').addEventListener('change', function (e) { setting().mode = e.target.value; renderAnalysis(); });
  byId('exportCsv').addEventListener('click', function () {
    save(filename(currentFile().name) + '_przebiegi.csv', new Blob([derivedCSV()], { type: 'text/csv;charset=utf-8' }));
  });
  byId('exportZip').addEventListener('click', exportReport);
  document.querySelectorAll('[data-svg]').forEach(function (el) { el.addEventListener('click', function () { exportChart(Number(el.getAttribute('data-svg')), 'svg'); }); });
  document.querySelectorAll('[data-png]').forEach(function (el) { el.addEventListener('click', function () { exportChart(Number(el.getAttribute('data-png')), 'png'); }); });
})();
