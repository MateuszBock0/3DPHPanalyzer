#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHP ANALYZER — pojedynczy plik do analizy temperatur 3D PHP (bez PCM).

INSTRUKCJA:
  1. Włóż TEN plik do folderu z surowymi plikami PicoLog *.csv
     (mogą też znajdować się w podfolderach lub w archiwum *.zip).
  2. Kliknij dwukrotnie php_analyzer.py lub uruchom: py php_analyzer.py
  3. Wyniki znajdziesz w folderze Results utworzonym obok programu.

Wymagania: Python 3.9+ i matplotlib (jednorazowo: py -m pip install matplotlib).
Program generuje wykresy PNG, raport HTML i tabele CSV.

WAŻNE: program nie czyta binarnych *.picolog — w tym celu należy wyeksportować
z PicoLog dane do CSV. Pliki źródłowe nigdy nie są nadpisywane.

UWAGI NAUKOWE:
  * Oscylacje temperatury ścianek nie dowodzą wprost ruchu cieczy i pary.
  * Zmiana ΔT nie jest dowodem zmiany przepływu, jeśli moc lub odbiór ciepła
    zmieniały się w czasie. Wyniki są KANDYDATAMI na rozruch.
  * Progi automatycznej detekcji są robocze, nie są normą branżową.
  * Jeden plik może mieć kilka poziomów mocy: nie przypisujemy mu wtedy jednej
    mocy ani nie wyliczamy arbitralnie oporu cieplnego (K/W).
  * Wykres R_wzgl (proxy) pokazuje ΔT/ΔT_ref w lokalnym okresie grzania.
    Jest równoważny R/R_ref TYLKO przy stałej mocy elektrycznej i podobnych
    warunkach strat/odbioru ciepła. Poziomy odniesienia są szacowane.

DOMYŚLNE KANAŁY z testów:
    Kanały 1 i 3 = parownik
    Kanały 4 i 5 = sekcja środkowa (odsłonięta)
    Kanały 6 i 7 = sekcja skraplacza / pusty pojemnik PCM
"""
from __future__ import annotations

import bisect
import csv
import datetime as _dt
import html
import io
import math
import os
import re
import statistics
import sys
import traceback
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import matplotlib
if os.environ.get('PHP_ANALYZER_GUI') != '1':
    matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# PARAMETRY DO EWENTUALNEJ ZMIANY (program działa bez ich zmieniania):
CHANNELS = (1, 3, 4, 5, 6, 7)
WINDOW_TREND_S = 121     # sekundy — usunięcie powolnej składowej temperatury
WINDOW_ACTIVITY_S = 120  # sekundy — okno RMS
WINDOW_DELTA_S = 60      # sekundy — wygładzenie ΔT
RMS_THRESHOLD_C = 1.0    # minimalny poziom wahań obu kanałów parownika
MIN_EPISODE_S = 120      # epizod musi trwać min. 2 minuty
MAX_GAP_S = 60           # połącz epizody rozdzielone przerwą <= 60 s
PRE_BASELINE_START_S = 360  # lokalna baza: od 6 min przed epizodem
PRE_BASELINE_END_S = 60     # do 1 min przed epizodem
MIN_BASELINE_S = 90
DELTA_IMPROVEMENT = 0.15  # próg roboczy poprawy ΔT: 15%
MIN_IMPROVEMENT_S = 300   # utrzymywanie poprawy >= 5 min
PEAK_PROMINENCE_C = 1.5  # oscylacje nie mogą być pojedynczym skokiem
MIN_PEAKS = 3
PLOT_MAX_POINTS = 1700
EXPORT_EVERY_S = 5        # co ile sekund zapisać przebieg pomocniczy CSV
BOTTOM_PANEL = 'RELATIVE_R'   # 'RELATIVE_R' (domyślnie) lub 'RMS'
RELATIVE_MIN_BASELINE_K = 5.0
RELATIVE_WARMUP_S = 300     # początki cykli grzania: brak interpretacji względnego R
RELATIVE_MIN_FRACTION = 0.65  # nie pokazuj względnego R w fazie mocnego dogrzewania
HEAT_CHANGE_WINDOW_S = 240  # porównanie zmian przez 4 minuty
HEAT_CHANGE_MIN_SEPARATION_S = 600  # odstęp tylko między ZDARZENIAMI TEGO SAMEGO RODZAJU
HEAT_PLATEAU_TOLERANCE_C = 1.0  # +-1 C: lokalnie stabilny poziom temperatury
HEAT_PLATEAU_WINDOW_S = 50      # ile sekund stabilnego poziomu wymagamy przed zmianą
HEAT_RESPONSE_SUSTAIN_S = 20    # odchylenie 1 C powinno utrzymac sie przynajmniej 20 s
HEAT_BAND_MARGIN_S = 15         # margines na szum/wygładzanie, NIE błąd czasu załączenia


COL = {
    'ev': '#C84D3A', 'middle': '#9C7D4B', 'co': '#2380BA',
    'dt': '#294E75', 'rms': '#AB643A', 'green': '#168B71',
    'amber': '#D09537', 'gray': '#778695', 'grid': '#DCE4E9'
}

@dataclass
class Record:
    name: str
    origin: str
    t: list[float]
    values: list[tuple[float, float, float, float, float, float]]
    bad_rows: int = 0
    fragment_of: str = ''

@dataclass
class Episode:
    number: int
    start_idx: int
    end_idx: int
    start: float
    end: float
    kind: str
    oscillatory: bool
    k2: bool
    peaks: int
    troughs: int
    baseline: float | None
    median_delta: float
    reduction_pct: float | None
    t_ev: float
    t_middle: float
    t_co: float
    rms_max: float
    improvement_duration_s: float
    pair_corr: float | None
    display_id: str = ""
    from_heating_on_s: float | None = None

@dataclass
class HeatingEvent:
    time: float
    kind: str   # HEATING_ON_EST / HEATING_OFF_EST / HEATING_INCREASE_EST
    t_ev: float
    t_co: float
    te_change: float
    tc_change: float
    band_start: float | None = None   # początek przedziału przypuszczalnego przejścia cieplnego
    band_end: float | None = None     # koniec przedziału; NIE przedział pewnego stanu grzałki
    t_before: float | None = None    # mediana z stabilnego poziomu parownika przed zmianą
    t_after: float | None = None     # mediana poziomu ustalonego po zmianie (jeśli znaleziony)
    method: str = 'BRAK_PLATEAU'


@dataclass
class Analysis:
    record: Record
    te: list[float]
    tm: list[float]
    tc: list[float]
    delta: list[float]
    delta_smooth: list[float]
    activity: list[float]
    threshold: float
    episodes: list[Episode]
    notes: list[str]
    heating_events: list[HeatingEvent]
    r_rel_proxy: list[float | None]
    r_rel_ref: list[float | None]


def safe_name(text: str) -> str:
    text = re.sub(r'[^\w.\-]+', '_', text, flags=re.UNICODE).strip('._')
    return text[:105] or 'pomiar'


def fmt(x: float | None, digits: int = 2) -> str:
    return '' if x is None or not math.isfinite(x) else f'{x:.{digits}f}'


def parse_time(value: str) -> float:
    x = value.strip().replace(',', '.')
    fields = x.split(':')
    if len(fields) == 3:
        return float(fields[0]) * 3600 + float(fields[1]) * 60 + float(fields[2])
    if len(fields) == 2:
        return float(fields[0]) * 60 + float(fields[1])
    return float(fields[0])


def unwrap_midnight_clock(t_seconds: list[float]) -> list[float]:
    """Unwrap unmistakable HH:MM:SS midnight rolls, preserving acquisition order.

    A large jump 20:00–24:00 -> 00:00–04:00 is interpreted as a day change.
    Other backward jumps are NOT silently treated as a new day. For absolute
    elapsed times >24 h no rollover is applied unless the clock resets.
    """
    out = []
    offset = 0.
    prev = None
    for raw in t_seconds:
        if prev is not None and (20 * 3600 <= prev < 24 * 3600
                                 and 0 <= raw <= 4 * 3600
                                 and prev - raw >= 12 * 3600):
            offset += 86400.
        out.append(raw + offset)
        prev = raw
    return out


def parse_csv(data: bytes, name: str, origin: str) -> Record:
    content = data.decode('utf-8-sig', errors='replace')
    # Export PicoLog has comma separators and decimal commas in quoted cells.
    # Allow semicolon-separated exports too.
    first_line = content.splitlines()[0] if content.splitlines() else ''
    delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration as e:
        raise ValueError('Pusty plik') from e
    channel_pos = {}
    for j, title in enumerate(header):
        match = re.search(r'(?:kana[łl]|channel)\s*(\d+)\b', title, flags=re.IGNORECASE)
        if match:
            channel_pos[int(match.group(1))] = j
    missing = [ch for ch in CHANNELS if ch not in channel_pos]
    if missing:
        raise ValueError('Brak kanałów: ' + ', '.join(map(str, missing)))
    tt, yy, bad = [], [], 0
    for row in reader:
        try:
            current = parse_time(row[0])
            vals = tuple(float(row[channel_pos[ch]].strip().replace(',', '.')) for ch in CHANNELS)
            if not math.isfinite(current) or not all(math.isfinite(v) for v in vals):
                raise ValueError('Niepoprawna liczba')
            tt.append(current)
            yy.append(vals)
        except (ValueError, IndexError):
            bad += 1
    if len(tt) < 120:
        raise ValueError('Mniej niż 120 poprawnych próbek')
    tt = unwrap_midnight_clock(tt)
    if any(b < a for a, b in zip(tt, tt[1:])):
        pairs = sorted(zip(tt, yy), key=lambda p: p[0])
        tt, yy = [x[0] for x in pairs], [x[1] for x in pairs]
    # Remove exact timestamp duplicates; keep the last reading.
    if any(b == a for a, b in zip(tt, tt[1:])):
        clean_t, clean_y = [], []
        for t, y in zip(tt, yy):
            if clean_t and t == clean_t[-1]:
                clean_y[-1] = y
            else:
                clean_t.append(t)
                clean_y.append(y)
        tt, yy = clean_t, clean_y
    if len(tt) < 120:
        raise ValueError('Zbyt mało unikalnych czasów pomiaru')
    return Record(name, origin, tt, yy, bad)


def find_inputs(folder: Path):
    """Search next to .py, recursively, excluding generated Results."""
    items = []
    ignored = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or any(part.lower() == 'results' for part in path.relative_to(folder).parts):
            continue
        if path.suffix.lower() == '.csv':
            items.append((str(path.relative_to(folder)), str(path.relative_to(folder)), path.read_bytes()))
        elif path.suffix.lower() == '.zip':
            try:
                with zipfile.ZipFile(path) as z:
                    for entry in sorted(z.namelist()):
                        if entry.lower().endswith('.csv') and not entry.endswith('/') and '/Results/' not in '/' + entry:
                            items.append((str(Path(entry).name), f'{path.name} / {entry}', z.read(entry)))
            except (zipfile.BadZipFile, OSError) as exc:
                ignored.append(f'Archiwum {path.name}: {exc}')
        elif path.suffix.lower() in ('.picolog', '.xlsx'):
            ignored.append(f'{path.name}: nieanalizowany format {path.suffix} (analiza temperatur korzysta z CSV)')
    return items, ignored


def unique_records(items):
    records, errors = [], []
    used = Counter()
    for raw_name, origin, data in items:
        base = Path(raw_name).name
        used[base] += 1
        name = base if used[base] == 1 else f'{Path(base).stem}__{used[base]}{Path(base).suffix}'
        try:
            records.append(parse_csv(data, name, origin))
        except Exception as e:
            errors.append(f'{origin}: {e}')
    for i, a in enumerate(records):
        for j, b in enumerate(records):
            if i == j or len(a.t) > len(b.t) or (len(a.t) == len(b.t) and j <= i):
                continue
            n = len(a.t)
            # Prefix matching catches the shorter export of the same measurement.
            probes = sorted(set([0, n-1, n//2, *range(0, min(n, 150), 5)]))
            if all(a.t[k] == b.t[k] and a.values[k] == b.values[k] for k in probes):
                a.fragment_of = b.name
                break
    return records, errors


def moving_average(y: list[float], win: int) -> list[float]:
    """Centered moving average, O(n)."""
    n = len(y)
    prefix = [0.0] * (n + 1)
    for i, v in enumerate(y):
        prefix[i+1] = prefix[i] + v
    radius = max(1, win // 2)
    output = []
    for i in range(n):
        a = max(0, i - radius)
        b = min(n, i + radius + 1)
        output.append((prefix[b] - prefix[a]) / (b-a))
    return output


def approx_window(s: float, sampling_s: float) -> int:
    return max(3, round(s / sampling_s))


def recording_segments(t: list[float], sampling_s: float | None = None):
    """Find contiguous measured intervals, and missing-time intervals.

    Boundaries are derived from actual timestamps, not from temperature changes.
    A gap is not proof that heating was switched off while the logger was silent.
    Returns: (list[(start_idx, end_idx_exclusive)], list[(t_before,t_after)]).
    """
    if not t:
        return [], []
    if sampling_s is None:
        sampling_s = median([b-a for a,b in zip(t,t[1:]) if b>a]) or 1.0
    limit = max(10.0, 5.0*sampling_s)
    gaps=[]
    pieces=[]
    start=0
    for i in range(1,len(t)):
        if t[i] - t[i-1] > limit:
            pieces.append((start,i))
            gaps.append((t[i-1],t[i]))
            start=i
    pieces.append((start,len(t)))
    return pieces, gaps


def segmented_average(y: list[float], win: int, segments):
    """Centered smoothing strictly within measured segments (never across missing data)."""
    result=[0.0]*len(y)
    for begin,end in segments:
        result[begin:end]=moving_average(y[begin:end], win)
    return result


def median(values):
    return statistics.median(values) if values else None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    a = sorted(values)
    return a[min(len(a)-1, max(0, round(q * (len(a)-1))))]


def mask_segments(t: list[float], mask: list[bool], min_s: float, gap_s: float):
    ranges = []
    start = end = None
    for i, marked in enumerate(mask):
        if not marked:
            continue
        if start is None:
            start = i
        elif t[i] - t[end] > gap_s:
            if t[end] - t[start] >= min_s:
                ranges.append((start, end))
            start = i
        end = i
    if start is not None and t[end] - t[start] >= min_s:
        ranges.append((start, end))
    return ranges


def local_extrema(x: list[float], threshold: float, min_sep: int) -> tuple[int, int]:
    """Count distinct peaks and troughs with a simple local prominence test."""
    # Compared with nearest local ±10 samples; isolated level changes do not
    # produce alternating peaks and troughs.
    peaks, dips = [], []
    r = max(2, min_sep)
    for i in range(r, len(x)-r):
        left, right = x[i-r:i], x[i+1:i+r+1]
        if x[i] >= max(left) and x[i] >= max(right) and x[i] - max(min(left), min(right)) >= threshold:
            if not peaks or i-peaks[-1] >= min_sep:
                peaks.append(i)
        if x[i] <= min(left) and x[i] <= min(right) and min(max(left), max(right)) - x[i] >= threshold:
            if not dips or i-dips[-1] >= min_sep:
                dips.append(i)
    return len(peaks), len(dips)


def correlation(x: list[float], y: list[float]) -> float | None:
    if len(x) < 10:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    dx, dy = [a-mx for a in x], [b-my for b in y]
    den = math.sqrt(sum(a*a for a in dx) * sum(b*b for b in dy))
    return sum(a*b for a, b in zip(dx, dy))/den if den > 1e-10 else None



def bracket_thermal_transition(t: list[float], te_smooth: list[float],
                               event: HeatingEvent, last_limit: float | None = None):
    """Wyznacz przedział zauważalnej reakcji temperatury parownika.

    Szuka ostatniego stabilnego poziomu +-1 C przed zmianą (50 s), po czym
    pierwszego trwale przekroczonego poziomu o 1 C. Zakres *nie* jest
    przedziałem, w którym na pewno przełączono elektrycznie grzałkę —
    bez logu zasilacza opóźnienia bezwładności cieplnej są nieznane.
    Przy braku stabilnego plateau pozostawia szeroki zakres pomocniczy.
    """
    direction = -1 if event.kind == 'HEATING_OFF_EST' else 1
    approx_idx = bisect.bisect_left(t, event.time)
    step = median([b-a for a,b in zip(t[max(0,approx_idx-80):min(len(t),approx_idx+80)],
                                 t[max(0,approx_idx-80):min(len(t),approx_idx+80)][1:]) if b>a]) or 1.0
    min_window = max(6,int(HEAT_PLATEAU_WINDOW_S / step))
    # Dla oszacowanego początku reakcji szukamy bliskiego plateau przed nim.
    # Obserwacji po przerwie w pomiarze nie łączymy z poprzednimi.
    search_from = bisect.bisect_left(t, event.time - 200)
    if last_limit is not None:
        search_from = max(search_from, bisect.bisect_left(t, last_limit + 1))
    stable = None
    for end in range(approx_idx, search_from+min_window-1, -1):
        begin = end-min_window+1
        if begin < search_from or t[end]-t[begin] > HEAT_PLATEAU_WINDOW_S*1.6:
            continue
        block=te_smooth[begin:end+1]
        # wymagane plateau: <= 1 C calkowitego rozrzutu i mały dryf
        if max(block)-min(block) <= HEAT_PLATEAU_TOLERANCE_C and abs(block[-1]-block[0]) <= 0.55:
            stable=(begin,end,statistics.median(block))
            break
    if stable is None:
        # Gdy nie ma stabilizacji, można podać jedynie zakres orientacyjny.
        event.band_start=max(t[0],event.time-45)
        event.band_end=min(t[-1],event.time+45)
        event.method='BEZ_PLATEAU_ORIENTACYJNIE'
        return
    sb,se,baseline=stable
    event.t_before=baseline
    for i in range(se+1, min(len(t),bisect.bisect_right(t,event.time+150))):
        if (t[i]-t[i-1]) > max(10,5*step):
            break
        if direction*(te_smooth[i]-baseline) < HEAT_PLATEAU_TOLERANCE_C:
            continue
        after=bisect.bisect_left(t,t[i]+HEAT_RESPONSE_SUSTAIN_S)
        if after >= len(t) or t[after]-t[i]>HEAT_RESPONSE_SUSTAIN_S+max(8,4*step):
            continue
        if all(direction*(te_smooth[k]-baseline)>=HEAT_PLATEAU_TOLERANCE_C
               for k in range(i,after+1)):
            event.band_start=max(t[se],t[i]-HEAT_BAND_MARGIN_S-HEAT_PLATEAU_WINDOW_S*0.5)
            event.band_end=min(t[-1],t[i]+HEAT_BAND_MARGIN_S)
            event.time=t[i]        # czas początku WIDOCZNEJ reakcji >1 C
            event.method='PLATEAU_PLUS_MINUS_1C'
            return
    event.band_start=max(t[se], event.time-40)
    event.band_end=min(t[-1],event.time+45)
    event.method='PLATEAU_BEZ_JEDNOZNACZNEGO_PROGU'


def fill_after_plateaus(t: list[float], sm_te: list[float], events: list[HeatingEvent]):
    """Znajdź dopiero po przejściu plateau po stronie końcowej, jeśli istnieje."""
    for e, nxt in zip(events, events[1:]+[None]):
        if e.t_before is None:
            continue
        left=bisect.bisect_left(t, e.time+150)
        right=bisect.bisect_left(t, min(t[-1],nxt.time-30 if nxt else e.time+3600))
        direction = -1 if e.kind == 'HEATING_OFF_EST' else 1
        win=90
        # plateau końcowe nie jest konieczne (np. pomiar urwany w czasie nagrzewania)
        for i in range(left, max(left,right-win), 12):
            j=bisect.bisect_left(t,t[i]+win)
            if j>=right or j>=len(t) or t[j]-t[i] > win+10:
                continue
            block=sm_te[i:j+1]
            med=statistics.median(block)
            if (max(block)-min(block) <= 1.0 and
                direction*(med-e.t_before) >= 3.0):
                e.t_after=med
                break

def estimate_heating_events(t: list[float], te: list[float], tc: list[float],
                            episodes: list[Episode]) -> list[HeatingEvent]:
    """Szacuje istotne przejścia grzanie/chłodzenie, NIE faktyczne stany grzałki.

    Kandydat wymaga jednokierunkowej, utrzymanej przez ok. 4 min reakcji
    parownika i skraplacza. Okna zawierające luki w rejestracji są pomijane.
    Odrzucamy punkty wewnątrz wcześniej rozpoznanych epizodów oscylacyjnych.
    """
    if len(t) < 500:
        return []
    step = median([b-a for a,b in zip(t,t[1:]) if b>a]) or 1.0
    smooth_n = approx_window(31,step)
    # Nie wolno filtrować przez luki pomiarowe: wygładzanie przez 58 minut
    # przerwy mogłoby stworzyć fałszywy skok w miejscu wznowienia zapisu.
    large_gap = [0]
    for i in range(1,len(t)):
        large_gap.append(large_gap[-1] + int(t[i]-t[i-1] > max(10.0,5*step)))
    sm_e = [0.0]*len(te)
    sm_c = [0.0]*len(tc)
    begin=0
    for stop in [i for i in range(1,len(t)) if large_gap[i]!=large_gap[i-1]] + [len(t)]:
        sm_e[begin:stop] = moving_average(te[begin:stop],smooth_n)
        sm_c[begin:stop] = moving_average(tc[begin:stop],smooth_n)
        begin=stop

    osc_intervals = [(e.start-30, e.end+30) for e in episodes if e.oscillatory]
    potential = []
    i = 0
    # co ok. 5 s: wygładzony sygnał temperatury i spójny kierunek zmian
    while i < len(t):
        ti=t[i]
        j=bisect.bisect_left(t,ti+HEAT_CHANGE_WINDOW_S)
        left=bisect.bisect_left(t,ti-30)
        right=bisect.bisect_left(t,ti+30)
        if j>=len(t) or right>=len(t) or left==right:
            i += max(1,round(5/step))
            continue
        if abs(t[j]-ti-HEAT_CHANGE_WINDOW_S)>max(8,4*step) or large_gap[j]!=large_gap[i]:
            i += max(1,round(5/step))
            continue
        if large_gap[right]!=large_gap[left]:
            i += max(1,round(5/step))
            continue
        de=sm_e[j]-sm_e[i]
        dc=sm_c[j]-sm_c[i]
        deriv=(sm_e[right]-sm_e[left])/(t[right]-t[left])*60
        kind=None
        # Brak oznaczenia zmiany, jeżeli sygnały reagują przeciwstawnie
        # (często właśnie podczas rozruchu PHP).
        if deriv>2.5 and de>=12.0 and dc>=2.5:
            kind='HEATING_ON_EST'
        elif deriv<-2.5 and de<=-18.0 and dc<=-2.5:
            kind='HEATING_OFF_EST'
        else:
            # Szybki OFF: gwałtowny, utrzymany spadek T_e może poprzedzać
            # chłodzenie skraplacza. Nie wymagamy wtedy -2.5 C na T_c
            # w pełnym oknie, ale wymagamy braku wyraźnego wzrostu T_c.
            # Ruch PHP często daje PRZECIWNE trendy: T_e spada, T_c rośnie.
            jshort=bisect.bisect_left(t,ti+90)
            if (jshort<len(t) and large_gap[jshort]==large_gap[i]
                    and abs(t[jshort]-ti-90)<max(8,4*step)
                    and sm_e[jshort]-sm_e[i] <= -10.0
                    and sm_c[jshort]-sm_c[i] <= -0.35
                    and de <= -14.0 and dc <= -0.8
                    and deriv < -3.0
                    and sm_e[j] <= sm_e[jshort]+1.5):
                kind='HEATING_OFF_EST'
        if kind and not any(a<=ti<=b for a,b in osc_intervals):
            potential.append((ti,kind,de,dc,i))
        i += max(1,round(5/step))

    # Grupy kolejnych podobnych kandydatów = jedno przejście.
    groups=[]
    for point in potential:
        if groups and point[1]==groups[-1][-1][1] and point[0]-groups[-1][-1][0]<=75:
            groups[-1].append(point)
        else:
            groups.append([point])
    events=[]
    for group in groups:
        start,kind,de,dc,idx=group[0]
        # Biegnące okno +/-30 s może zasygnalizować zmianę odrobinę
        # wcześniej niż rzeczywisty moment przełączenia.
        if kind=='HEATING_ON_EST' and te[idx]-tc[idx] > 8.0:
            # PHP jest już gorąca: raczej zwiększenie obciążenia niż
            # nowe uruchomienie zasilania od zera.
            kind='HEATING_INCREASE_EST'
        if kind=='HEATING_OFF_EST' and te[idx]-tc[idx] < 8.0:
            # Nie można mówić o wyłączeniu przy wyrównanych temperaturach.
            continue
        if events and start-events[-1].time < HEAT_CHANGE_MIN_SEPARATION_S:
            # Ograniczenie 10 min dotyczy duplikatów tego samego kierunku
            # zmiany, a NIE przeciwstawnych przejść ON -> OFF / OFF -> ON.
            # Krótka, np. czterominutowa próba grzania jest dopuszczalna.
            previous_is_heating = events[-1].kind in ('HEATING_ON_EST','HEATING_INCREASE_EST')
            candidate_is_heating = kind in ('HEATING_ON_EST','HEATING_INCREASE_EST')
            if previous_is_heating == candidate_is_heating:
                continue
        events.append(HeatingEvent(start,kind,te[idx],tc[idx],de,dc))
    # Zmierz początek widocznej zmiany względem lokalnego plateau (+-1 C).
    # Nie przenoś plateau ani progów przez realne luki w rejestracji.
    segments,_=recording_segments(t,step)
    for ev in events:
        segment_begin=next((t[a] for a,b in segments if t[a] <= ev.time <= t[b-1]),t[0])
        bracket_thermal_transition(t,sm_e,ev,segment_begin-1)
    events.sort(key=lambda e:e.time)
    fill_after_plateaus(t,sm_e,events)
    return events


def last_heating_on(heating_events: list[HeatingEvent], event_time: float) -> float | None:
    active=None
    for event in heating_events:
        if event.time > event_time:
            break
        if event.kind=='HEATING_ON_EST':
            active=event.time
        elif event.kind=='HEATING_OFF_EST':
            active=None
    return active


def relative_resistance_proxy(t: list[float], delta_smooth: list[float],
                              heating_events: list[HeatingEvent],
                              episodes: list[Episode]):
    """Wskaźnik ΔT/ΔT_ref na OSZACOWANYCH etapach grzania.

    Dla stałej mocy i porównywalnych warunków strat jest równy R_app/R_ref.
    Nie jest rzeczywistym oporem cieplnym: moc nie została zarejestrowana.
    Odniesienie: lokalne ΔT przed oscylacją albo 90. percentyl spokojnych
    pomiarów w danym cyklu. Czasy między ON/OFF i moc są estymowane.
    """
    rr = [None] * len(t)
    refs = [None] * len(t)
    if not heating_events:
        return rr, refs
    # Oszacowane cykle, z rozdzieleniem każdej szacowanej zmiany obciążenia.
    windows = []
    active = None
    for ev in sorted(heating_events, key=lambda e: e.time):
        if ev.kind in ('HEATING_ON_EST','HEATING_INCREASE_EST'):
            if active is not None and ev.time > active:
                windows.append((active, ev.time))
            active = ev.time
        elif ev.kind == 'HEATING_OFF_EST' and active is not None:
            if ev.time > active:
                windows.append((active, ev.time))
            active = None
    if active is not None:
        windows.append((active, t[-1]))

    measurement_segments, _ = recording_segments(t)
    for ton, toff in windows:
        eps = [ep for ep in episodes if ep.oscillatory and ton <= ep.start < toff
               and ep.baseline is not None and ep.baseline >= RELATIVE_MIN_BASELINE_K]
        # Keep local baseline from the first oscillation in this cycle if present.
        reference = eps[0].baseline if eps else None
        if reference is None:
            exclude = [(ep.start-60, ep.end+60) for ep in episodes if ep.oscillatory]
            candidates = [d for tt, d in zip(t, delta_smooth)
                          if ton+RELATIVE_WARMUP_S <= tt <= toff-30
                          and d > RELATIVE_MIN_BASELINE_K
                          and not any(a <= tt <= b for a,b in exclude)]
            if len(candidates) < 12:
                continue
            reference = percentile(candidates, 0.90)
        if reference is None or reference < RELATIVE_MIN_BASELINE_K:
            continue

        # Nie łącz pomiarów przez przerwy w rejestracji. Dla odcinka po luce
        # od nowa obowiązuje minimalny czas od pierwszego zarejestrowanego
        # punktu — nawet jeśli ON było wcześniej.
        for begin, end in measurement_segments:
            if end <= begin or t[end-1] < ton or t[begin] > toff:
                continue
            begin_t = max(ton+RELATIVE_WARMUP_S, t[begin]+RELATIVE_WARMUP_S
                          if t[begin] > ton+30 else ton+RELATIVE_WARMUP_S)
            for i in range(begin, end):
                if not (begin_t <= t[i] <= toff):
                    continue
                value = delta_smooth[i]
                if value < RELATIVE_MIN_FRACTION*reference:
                    # Niskie ΔT zaraz po rozgrzaniu nie jest wynikiem rozruchu.
                    # Ale jeśli zdarzenie już trwa, spadek jest prawdziwą
                    # obserwacją i nie wolno go maskować.
                    inside_osc = any(ep.start <= t[i] <= ep.end for ep in eps)
                    if not inside_osc:
                        continue
                rr[i] = value/reference
                refs[i] = reference
    return rr, refs


def analyze(rec: Record) -> Analysis:
    t, v = rec.t, rec.values
    te = [(q[0]+q[1])/2 for q in v]
    tm = [(q[2]+q[3])/2 for q in v]
    tc = [(q[4]+q[5])/2 for q in v]
    delta = [e-c for e,c in zip(te,tc)]
    step = median([b-a for a,b in zip(t,t[1:]) if b>a]) or 1.0
    segments, gaps = recording_segments(t, step)
    ntrend = approx_window(WINDOW_TREND_S, step)
    nact = approx_window(WINDOW_ACTIVITY_S, step)
    ch1=[q[0] for q in v]
    ch3=[q[1] for q in v]
    res1 = [a-b for a,b in zip(ch1, segmented_average(ch1, ntrend, segments))]
    res3 = [a-b for a,b in zip(ch3, segmented_average(ch3, ntrend, segments))]
    var1 = segmented_average([x*x for x in res1], nact, segments)
    var3 = segmented_average([x*x for x in res3], nact, segments)
    # Conservative: both evaporator thermocouples must move.
    rms = [min(math.sqrt(max(0., a)), math.sqrt(max(0., b))) for a,b in zip(var1, var3)]
    quiet_end = min(t[0]+min(180, .1*(t[-1]-t[0])), t[-1])
    quiet_rms = [y for s,y in zip(t,rms) if s<=quiet_end]
    base_noise = percentile(quiet_rms, .9) if quiet_rms else 0.0
    threshold = max(RMS_THRESHOLD_C, 3*base_noise)
    k1 = [x>=threshold for x in rms]
    # Detect episodes inside independent measurement segments. A gap must
    # never be counted as a prolonged oscillation or improve K2 duration.
    ranges=[]
    for begin,end in segments:
        ranges += [(begin+i,begin+j) for i,j in mask_segments(
            t[begin:end],k1[begin:end],MIN_EPISODE_S,MAX_GAP_S)]
    dsmooth = segmented_average(delta, approx_window(WINDOW_DELTA_S, step), segments)
    notes = []
    if rec.fragment_of:
        notes.append('FRAGMENT INNEGO ZAPISU: ' + rec.fragment_of + ' (nie traktować jako niezależnego testu)')
    if rec.bad_rows:
        notes.append(f'Pominięto nieprawidłowe wiersze CSV: {rec.bad_rows}')
    for idx, ch in enumerate(CHANNELS):
        limit=max(10.0,5*step)
        big = sum(1 for i in range(1,len(v))
                  if t[i]-t[i-1]<=limit and abs(v[i][idx]-v[i-1][idx])>5)
        if big:
            notes.append(f'Kanał {ch}: {big} skoków >5°C między sąsiednimi próbkami; sprawdź czujnik lub zdarzenia.')
    if gaps:
        longest=max(right-left for left,right in gaps)
        notes.append(f'BRAKI DANYCH: {len(gaps)} przerw rejestracji; najdłuższa {longest:.0f} s. '
                     'Luki nie są łączone liniami ani uwzględniane w obliczaniu RMS/ΔT.')
    episodes = []
    for count, (i,j) in enumerate(ranges, 1):
        start, end = t[i], t[j]
        # Look for repeated shape, not a single heating-power step.
        # Remove a further local short trend in the episode itself.
        osc = res1[i:j+1]
        osc_b = res3[i:j+1]
        min_sep = max(3, round(8/step))
        np1, nt1 = local_extrema(osc, PEAK_PROMINENCE_C, min_sep)
        np3, nt3 = local_extrema(osc_b, PEAK_PROMINENCE_C, min_sep)
        peak_count, trough_count = min(np1, np3), min(nt1, nt3)
        oscillatory = peak_count >= MIN_PEAKS and trough_count >= MIN_PEAKS
        local_begin=next((a for a,b in segments if a<=i<b),0)
        local_before=[delta[k] for k in range(local_begin,i)
                      if start-PRE_BASELINE_START_S<=t[k]<=start-PRE_BASELINE_END_S]
        baseline = median(local_before) if len(local_before)*step >= MIN_BASELINE_S else None
        # When ΔT is close to ambient equilibrium, a percentage reduction
        # is meaningless and becomes arbitrarily large.
        if baseline is not None and baseline < 5.0:
            baseline = None
        med_delta = statistics.median(delta[i:j+1])
        improvement = 100*(1 - med_delta/baseline) if baseline else None
        supported_time = 0.
        if baseline:
            k2_local = [x <= baseline*(1-DELTA_IMPROVEMENT) for x in dsmooth[i:j+1]]
            improved_spans = mask_segments(t[i:j+1], k2_local, MIN_IMPROVEMENT_S, max(10, 3*step))
            supported_time = sum(t[i+b]-t[i+a] for a,b in improved_spans)
        k2 = oscillatory and supported_time>=MIN_IMPROVEMENT_S
        kind = ('OSC_AND_DELTA_IMPROVEMENT' if k2 else
                'OSC_ONLY' if oscillatory else
                'THERMAL_TRANSIENT')
        episodes.append(Episode(count, i, j, start, end, kind, oscillatory, k2,
                                peak_count, trough_count, baseline, med_delta,
                                improvement, median(te[i:j+1]) or 0.,
                                median(tm[i:j+1]) or 0., median(tc[i:j+1]) or 0.,
                                max(rms[i:j+1]), supported_time,
                                correlation(res1[i:j+1],res3[i:j+1])))
    heating_events=estimate_heating_events(t,te,tc,episodes)
    osc_no=0
    transient_no=0
    for ep in episodes:
        if ep.oscillatory:
            osc_no+=1
            ep.display_id=f'O{osc_no}'
            current_on=last_heating_on(heating_events,ep.start)
            if current_on is not None:
                ep.from_heating_on_s=ep.start-current_on
        else:
            transient_no+=1
            ep.display_id=f'T{transient_no}'
    notes.append('ON?/OFF? = reakcja cieplna, nie elektryczny zapis ON/OFF; pasma +-1°C wskazują orientacyjny przedział początku reakcji.')
    notes.append('Moc nie jest automatycznie przypisywana: jeden plik może zawierać kilka nastaw grzałki.')
    notes.append('K1: aktywność obu termopar parownika, K2: spadek ΔT względem lokalnego okna poprzedzającego epizod.')
    notes.append('Oscylacje temperatur i K2 są przesłankami, a nie bezpośrednim dowodem ruchu czynnika w PHP.')
    rr, rr_ref = relative_resistance_proxy(t, dsmooth, heating_events, episodes)
    notes.append('R_wzgl (proxy): ΔT/ΔT_ref w oszacowanych cyklach grzania; tylko przy stałej mocy odpowiada R_app/R_ref. Nie jest to opór w K/W.')
    return Analysis(rec, te, tm, tc, delta, dsmooth, rms, threshold, episodes, notes,
                    heating_events, rr, rr_ref)


def write_csv(path: Path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)


def csv_summary(analyses: list[Analysis]):
    rows = []
    for r in analyses:
        evs = r.episodes
        oscillatory = [x for x in evs if x.oscillatory]
        k2 = [x for x in evs if x.k2]
        t = r.record.t
        rows.append({
            'plik': r.record.name,
            'zrodlo': r.record.origin,
            'fragment_innego_pliku': r.record.fragment_of,
            'liczba_probek': len(t),
            'czas_pomiaru_min': fmt((t[-1]-t[0])/60),
            'liczba_luk_rejestracji': len(recording_segments(t)[1]),
            'najdluzsza_luka_s': fmt(max((b-a for a,b in recording_segments(t)[1]),default=0),1),
            'T_parownik_max_C': fmt(max(r.te)),
            'T_srodek_max_C': fmt(max(r.tm)),
            'T_skraplacz_max_C': fmt(max(r.tc)),
            'DeltaT_max_K': fmt(max(r.delta)),
            'DeltaT_mediana_K': fmt(statistics.median(r.delta)),
            'liczba_zdarzen': len(evs),
            'liczba_epizodow_oscylacyjnych': len(oscillatory),
            'oscylacje_plus_poprawa_DeltaT': len(k2),
            'liczba_ponownych_aktywacji': max(0,len(oscillatory)-1),
            'ON_szacowane': sum(z.kind=='HEATING_ON_EST' for z in r.heating_events),
            'OFF_szacowane': sum(z.kind=='HEATING_OFF_EST' for z in r.heating_events),
            'czas_do_pierwszej_oscylacji_od_ON_min': fmt(oscillatory[0].from_heating_on_s/60 if oscillatory and oscillatory[0].from_heating_on_s is not None else None),
            'pierwszy_epizod_min_od_csv': fmt(oscillatory[0].start/60 if oscillatory else None),
            'laczny_czas_oscylacji_min': fmt(sum(e.end-e.start for e in oscillatory)/60),
            'udzial_czasu_oscylacji_pct': fmt(100*sum(e.end-e.start for e in oscillatory)/(t[-1]-t[0])),
            'status': ('OSC_PLUS_POPRAWA_DELTAT' if k2 else 'OSC_BEZ_POTWIERDZONEJ_POPRAWY' if oscillatory else 'TYLKO_PRZEJSCIA' if evs else 'BRAK_WYKRYTEGO_EPIZODU'),
            'uwagi': ' | '.join(r.notes),
        })
    return rows


def csv_episodes(analyses: list[Analysis], *, oscillatory_only: bool = False):
    rows = []
    for r in analyses:
        for e in r.episodes:
            if oscillatory_only and not e.oscillatory:
                continue
            rows.append({
                'plik': r.record.name, 'epizod': e.display_id,
                'fragment_innego_pliku': r.record.fragment_of,
                'status': e.kind,
                'powtarzajace_sie_oscylacje': int(e.oscillatory),
                'wspolna_poprawa_DeltaT_K2': int(e.k2),
                'poczatek_min_od_csv': fmt(e.start/60),
                'koniec_min_od_csv': fmt(e.end/60),
                'czas_trwania_min': fmt((e.end-e.start)/60),
                'czas_od_szacowanego_ON_min': fmt(e.from_heating_on_s/60 if e.from_heating_on_s is not None else None),
                'liczba_maksimow': e.peaks,
                'liczba_minimow': e.troughs,
                'T_parownik_mediana_C': fmt(e.t_ev),
                'T_srodek_mediana_C': fmt(e.t_middle),
                'T_skraplacz_mediana_C': fmt(e.t_co),
                'DeltaT_przed_epizodem_K': fmt(e.baseline),
                'DeltaT_w_epizodzie_K': fmt(e.median_delta),
                'redukcja_DeltaT_pct': fmt(e.reduction_pct),
                'K2_laczny_czas_min': fmt(e.improvement_duration_s/60),
                'RMS_maks_C': fmt(e.rms_max),
                'korelacja_parownika': fmt(e.pair_corr, 3),
            })
    return rows


def csv_heating_events(analyses: list[Analysis]):
    return [
        {
            'plik':r.record.name,
            'fragment_innego_pliku':r.record.fragment_of,
            'rodzaj_zdarzenia':e.kind,
            'czas_od_poczatku_CSV_min':fmt(e.time/60),
            'T_parownik_w_zdarzeniu_C':fmt(e.t_ev),
            'T_skraplacz_w_zdarzeniu_C':fmt(e.t_co),
            'zmiana_parownik_4min_C':fmt(e.te_change),
            'zmiana_skraplacz_4min_C':fmt(e.tc_change),
            'przedzial_od_min':fmt(e.band_start/60,3) if e.band_start is not None else '',
            'przedzial_do_min':fmt(e.band_end/60,3) if e.band_end is not None else '',
            'T_parownik_plateau_przed_C':fmt(e.t_before),
            'T_parownik_plateau_po_C':fmt(e.t_after),
            'metoda_przedzialu':e.method,
            'interpretacja':'Przedzial reakcji termicznej, NIE potwierdzony czas elektrycznego przełączenia',
        }
        for r in analyses for e in r.heating_events
    ]


def csv_gaps(analyses: list[Analysis]):
    rows=[]
    for r in analyses:
        for a,b in recording_segments(r.record.t)[1]:
            rows.append({
                'plik':r.record.name,
                'fragment_innego_pliku':r.record.fragment_of,
                'ostatnia_probka_przed_luka_min':fmt(a/60,4),
                'pierwsza_probka_po_luce_min':fmt(b/60,4),
                'czas_bez_danych_s':fmt(b-a,1),
                'uwaga':'Brak odczytów: przebieg temperatury i stan grzałki w luce są nieznane',
            })
    return rows


def export_series(r: Analysis, path: Path):
    rows = []
    times = r.record.t
    last_export = -float('inf')
    for i, t in enumerate(times):
        if t-last_export+1e-9 < EXPORT_EVERY_S and i != len(times)-1:
            continue
        last_export = t
        e = next((ep for ep in r.episodes if ep.oscillatory and ep.start<=t<=ep.end), None)
        q = r.record.values[i]
        rows.append({
            'czas_od_csv_min': fmt(t/60,4),
            **{f'T_ch{ch}_C':fmt(q[k],3) for k,ch in enumerate(CHANNELS)},
            'T_parownik_C':fmt(r.te[i],3),
            'T_srodek_C':fmt(r.tm[i],3),
            'T_skraplacz_C':fmt(r.tc[i],3),
            'DeltaT_K':fmt(r.delta[i],3),
            'DeltaT_wygladzone_K':fmt(r.delta_smooth[i],3),
            'RMS_aktywnosc_C':fmt(r.activity[i],3),
            'R_wzgledne_proxy_bezwymiarowe':fmt(r.r_rel_proxy[i],4),
            'DeltaT_odniesienia_K':fmt(r.r_rel_ref[i],3),
            'epizod':(e.display_id if e else ''),
            'rodzaj_epizodu':(e.kind if e else ''),
        })
    write_csv(path, rows, list(rows[0]))


def xml(text):
    return html.escape(str(text), quote=True)


def _episode_color(kind: str) -> str:
    return {'OSC_AND_DELTA_IMPROVEMENT': COL['green'], 'OSC_ONLY': COL['amber'], 'THERMAL_TRANSIENT': COL['gray']}.get(kind, COL['gray'])

def _nice_ylim(values, pad=0.06, min_span=1.0):
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if not finite:
        return (0.0, 1.0)
    vmin, vmax = min(finite), max(finite)
    span = max(min_span, vmax - vmin)
    extra = span * pad
    return (vmin - extra, vmax + extra)


def make_plot_png(r: Analysis, out_path: Path, start_s: float | None = None, end_s: float | None = None,
                  *, bottom_values=None, bottom_label=None, bottom_level_one=False):
    """Jednolity PNG: naglowek, trzy osobne panele i osobna stopka.

    Wszystkie opisy, legendy i podpis osi X maja zarezerwowane miejsce,
    dzieki czemu nie nakladaja sie na siebie na wydruku ani w HTML.
    """
    t = r.record.t
    xmin = t[0] if start_s is None else max(t[0], start_s)
    xmax = t[-1] if end_s is None else min(t[-1], end_s)
    if xmax <= xmin:
        xmin, xmax = t[0], t[-1]
    inds = [i for i, value in enumerate(t) if xmin <= value <= xmax]
    if not inds:
        inds = list(range(len(t)))
    # Wydajny wykres wielogodzinnego zapisu: zachowaj lokalne ekstrema,
    # ale nie rysuj dziesiątek tysięcy punktów w każdym PNG.
    # Analiza statystyczna nadal korzysta z pełnych, nieprzerzedzonych danych.
    if len(inds) > 5500:
        width = math.ceil(len(inds) / 1100)
        chosen={inds[0], inds[-1]}
        for k in range(0,len(inds),width):
            chunk=inds[k:k+width]
            chosen.update((chunk[0],chunk[-1]))
            chosen.add(min(chunk,key=lambda i:r.te[i]))
            chosen.add(max(chunk,key=lambda i:r.te[i]))
            chosen.add(min(chunk,key=lambda i:r.tc[i]))
            chosen.add(max(chunk,key=lambda i:r.tc[i]))
        # Nie wolno zgubić końców długich luk w rejestracji.
        for i in range(1,len(t)):
            if t[i]-t[i-1]>10 and xmin<=t[i]<=xmax:
                chosen.update((i-1,i))
        inds=sorted(chosen)

    x = [t[i] / 60 for i in inds]
    individual = [[r.record.values[i][j] for i in inds] for j in range(6)]
    te = [r.te[i] for i in inds]
    tm = [r.tm[i] for i in inds]
    tc = [r.tc[i] for i in inds]
    delta = [r.delta[i] for i in inds]
    dsmooth = [r.delta_smooth[i] for i in inds]
    activity = [r.activity[i] for i in inds]
    if bottom_values is not None and len(bottom_values) != len(t):
        raise ValueError('Nieprawidłowa długość trzeciego panelu eksportu.')
    relative_r = [(bottom_values[i] if bottom_values[i] is not None else math.nan)
                  for i in inds] if bottom_values is not None else [
                    r.r_rel_proxy[i] if r.r_rel_proxy[i] is not None else math.nan for i in inds]
    # Insert NaNs for display only. Plotting consecutive valid samples on
    # opposite sides of a long logger outage would falsely imply observed data.
    step=median([b-a for a,b in zip(t,t[1:]) if b>a]) or 1.0
    cut=max(10.0, 5.0*step)
    # Uwaga: przerzedzanie pikselowe NIE JEST luką rejestracji!
    # Zaznaczamy tylko prawdziwe przerwy w oryginalnych znacznikach czasu.
    true_gaps=[(t[i-1],t[i]) for i in range(1,len(t))
               if t[i]-t[i-1]>cut and t[i]>=xmin and t[i-1]<=xmax]
    gap_starts=[b for a,b in true_gaps]
    chart_positions=[]
    display_x=[]
    for j,idx in enumerate(inds):
        # Break line tylko gdy pomiędzy próbkami wystąpiła prawdziwa luka.
        if j and bisect.bisect_right(gap_starts,t[inds[j-1]]) < bisect.bisect_right(gap_starts,t[idx]):
            chart_positions.append(None)
            display_x.append((t[idx]+t[inds[j-1]])/120)
        chart_positions.append(j)
        display_x.append(t[idx]/60)
    def visible(values):
        return [math.nan if j is None else values[j] for j in chart_positions]
    missing_intervals=true_gaps

    # Rezerwujemy ODDZIELNE wiersze na tytul i stopke. Celowo nie
    # uzywamy fig.text + constrained_layout, ktore nakladalo napisy.
    fig = plt.figure(figsize=(15.5, 11.1), dpi=160, facecolor='white')
    gs = fig.add_gridspec(5, 1,
                          height_ratios=[0.75, 3.6, 2.25, 1.5, 0.48],
                          left=0.075, right=0.986, top=0.98, bottom=0.025,
                          hspace=0.34)
    header = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[1])
    ax2 = fig.add_subplot(gs[2], sharex=ax1)
    ax3 = fig.add_subplot(gs[3], sharex=ax1)
    footer = fig.add_subplot(gs[4])
    header.set_axis_off()
    footer.set_axis_off()
    axes = (ax1, ax2, ax3)

    header.text(0.5, 0.90, r.record.name, ha='center', va='center',
                fontsize=17, weight='bold', color='#1F2D3D')
    header.text(0.5, 0.53,
                '3D PHP — pusty pojemnik PCM | analiza temperatur | moc nieprzypisana automatycznie',
                ha='center', va='center', fontsize=10, color='#516272')
    handles = [
        Line2D([0], [0], color=COL['ev'], lw=2.3, label='Parownik (ch1, ch3)'),
        Line2D([0], [0], color=COL['middle'], lw=2.3, label='Sekcja środkowa (ch4, ch5)'),
        Line2D([0], [0], color=COL['co'], lw=2.3, label='Skraplacz (ch6, ch7)'),
        Line2D([0], [0], color=COL['ev'], lw=0.9, alpha=0.33, label='Pojedyncze termopary (cienkie linie)')
    ]
    header.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, -0.01),
                  ncol=4, frameon=False, fontsize=9.5, handlelength=2.5,
                  columnspacing=2.7)

    for before,after in missing_intervals:
        for ax in axes:
            ax.axvspan(before/60,after/60,facecolor='#9BA8B2',alpha=0.15,linewidth=0)
            ax.axvline(before/60,color='#8996A3',lw=0.8,alpha=0.5,linestyle=':')
            ax.axvline(after/60,color='#8996A3',lw=0.8,alpha=0.5,linestyle=':')
        duration=(after-before)/60
        if duration>=3:
            ax1.text((before+after)/120,0.55,f'BRAK DANYCH\n{duration:.1f} min',
                     transform=ax1.get_xaxis_transform(),ha='center',va='center',
                     color='#4D5D6B',fontsize=11,weight='bold',
                     bbox=dict(facecolor='white',edgecolor='none',alpha=0.75,pad=5))

    for ep in r.episodes:
        if not ep.oscillatory:
            continue
        left = max(xmin, ep.start) / 60.0
        right = min(xmax, ep.end) / 60.0
        if right <= left:
            continue
        color = _episode_color(ep.kind)
        for ax in axes:
            ax.axvspan(left, right, color=color, alpha=0.12, linewidth=0)
        ax1.text((left + right)/2, 0.986, ep.display_id,
                 transform=ax1.get_xaxis_transform(), ha='center', va='top',
                 fontsize=9, weight='bold', color=color,
                 bbox={'boxstyle': 'round,pad=0.18', 'facecolor': 'white',
                       'edgecolor': 'none', 'alpha': 0.80})

    # Jeśli ON i OFF są blisko siebie, rozsuń ich pionowe podpisy,
    # zamiast układać je obok siebie w tym samym miejscu.
    visible_heat = [e for e in r.heating_events
                    if xmin <= e.time <= xmax and e.kind != 'HEATING_INCREASE_EST']
    for k, ev in enumerate(visible_heat):
        is_on=ev.kind=='HEATING_ON_EST'
        shade='#5A6783' if is_on else '#8472A3'
        for ax in axes:
            if ev.band_start is not None and ev.band_end is not None:
                ax.axvspan(ev.band_start/60, ev.band_end/60,
                           facecolor=shade, alpha=0.14, lw=0)
                # Dwie krawędzie strefy niepewności reakcji temperaturowej.
                ax.axvline(ev.band_start/60,color=shade,lw=0.8,alpha=0.6,linestyle=':')
                ax.axvline(ev.band_end/60,color=shade,lw=0.8,alpha=0.6,linestyle=':')
            else:
                ax.axvline(ev.time/60, color=shade, linestyle=':', lw=1.2, alpha=0.6)
        near_prev = k>0 and ev.time-visible_heat[k-1].time < 7*60
        y_label = 0.75 if near_prev else 0.94
        ax1.annotate('ON?' if is_on else 'OFF?', xy=(ev.time/60, y_label),
                     xycoords=ax1.get_xaxis_transform(), xytext=(4,0),
                     textcoords='offset points', ha='left', va='top', fontsize=9,
                     color=shade, rotation=90, fontweight='bold')

    for j, values in enumerate(individual):
        color = COL['ev'] if j < 2 else COL['middle'] if j < 4 else COL['co']
        ax1.plot(display_x, visible(values), lw=0.75, color=color, alpha=0.28)
    ax1.plot(display_x, visible(te), color=COL['ev'], linewidth=2.2)
    ax1.plot(display_x, visible(tm), color=COL['middle'], linewidth=2.2)
    ax1.plot(display_x, visible(tc), color=COL['co'], linewidth=2.2)
    ax1.set_ylabel('Temperatura [°C]', fontsize=11, labelpad=9)
    ax1.set_ylim(*_nice_ylim([v for y in individual for v in y], pad=0.08, min_span=10))

    ax2.plot(display_x, visible(delta), color=COL['dt'], lw=1.0, alpha=0.45, label='ΔT chwilowe')
    ax2.plot(display_x, visible(dsmooth), color=COL['green'], lw=2.2, label='ΔT wygładzone')
    ax2.set_ylabel('ΔT = Te − Tc [K]', fontsize=11, labelpad=9)
    ax2.set_ylim(*_nice_ylim(delta + dsmooth, pad=0.08, min_span=8))
    ax2.legend(loc='upper left', fontsize=9, framealpha=0.88)

    if bottom_values is not None:
        if bottom_level_one:
            ax3.axhline(1.0, color='#768A9B', lw=1.1, linestyle='--', label='Odniesienie = 1')
        ax3.plot(display_x, visible(relative_r), color='#8248AE', lw=2.0,
                 drawstyle='steps-post' if bottom_label == 'Q [W]' else 'default',
                 label=bottom_label or 'Wybrana metryka')
        finite = [x for x in relative_r if math.isfinite(x)]
        ax3.set_ylim(*_nice_ylim(finite, pad=.09, min_span=0.5 if bottom_level_one else 1.0))
        ax3.set_ylabel(bottom_label or 'Wybrana metryka', fontsize=10, labelpad=9)
        if not finite:
            ax3.text(.5, .45, 'Brak wartości dla wybranego panelu / nieznana Q',
                     transform=ax3.transAxes, ha='center', va='center',
                     color='#6E7D8C', fontsize=10)
    elif BOTTOM_PANEL == 'RELATIVE_R':
        ax3.axhline(1.0, color='#768A9B', lw=1.1, linestyle='--',
                    label='Poziom odniesienia = 1')
        ax3.plot(display_x, visible(relative_r), color='#8248AE', lw=2.0,
                 label='ΔT / ΔT_ref (proxy R wzgl.)')
        non_nan = [v for v in relative_r if math.isfinite(v)]
        ax3.set_ylim(0, max(1.2, min(3.0, 1.08*max(non_nan,default=1.0))))
        ax3.set_ylabel('R wzgl. (proxy) [−]', fontsize=10, labelpad=9)
        if not non_nan:
            ax3.text(.5,.4,'Brak okresu grzania do wiarygodnej normalizacji',
                     ha='center',va='center',transform=ax3.transAxes,
                     color='#6E7D8C',fontsize=10)
    else:
        ax3.plot(display_x, visible(activity), color=COL['rms'], lw=1.8,
                 label='Aktywność RMS')
        ax3.axhline(r.threshold, color=COL['rms'], lw=1.3,
                    linestyle='--', label=f'Próg K1: {r.threshold:.2f} °C')
        ax3.set_ylabel('RMS [°C]', fontsize=11, labelpad=9)
        ax3.set_ylim(bottom=0, top=max(max(activity) * 1.12, r.threshold * 1.35, 1.0))
    ax3.legend(loc='upper left', fontsize=9, framealpha=0.88)
    ax3.set_xlabel('Czas od początku rejestracji CSV [min]', fontsize=11, labelpad=7)
    ax3.set_xlim(xmin/60, xmax/60)

    for ax in axes:
        ax.grid(True, color=COL['grid'], alpha=0.65, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(axis='both', labelsize=9.5, direction='out', length=3)
        for side in ax.spines.values():
            side.set_color('#8A98A6')
    ax1.tick_params(axis='x', labelbottom=False)
    ax2.tick_params(axis='x', labelbottom=False)

    footer.text(0.01, 0.78,
                'O1, O2…: epizody oscylacyjne   |   zielone tło: poprawa ΔT   |   pomarańczowe tło: brak potwierdzonej poprawy',
                ha='left', va='center', fontsize=9.2, color='#4A5969')
    footer.text(0.01, 0.30,
                ('Dolny panel: ' + (bottom_label or 'wybrana metryka') +
                  '. Q pochodzi z ustawień operatora; ON?/OFF? szacowane.'
                  if bottom_values is not None else
                  ('R wzgl. (proxy) = ΔT/ΔT_ref; odpowiada R/R_ref tylko przy stałej mocy. '
                   'ON?/OFF? szacowane; szare pasma: braki danych.'
                   if BOTTOM_PANEL == 'RELATIVE_R' else
                   'ON?/OFF?: estymacja z temperatur. Szare pasma = brak danych. Oscylacje nie dowodzą ruchu czynnika.')),
                ha='left', va='center', fontsize=9.2, color='#4A5969')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Bez bbox_inches='tight': wszystkie wykresy maja IDENTYCZNA
    # rozdzielczosc 2480 × 1776 pikseli.
    fig.savefig(out_path, dpi=160, facecolor='white')
    plt.close(fig)


def make_heating_diagnostics(r: Analysis, directory: Path):
    """Jeden PNG na pomiar: wszystkie szacowane początki reakcji w powiększeniu.

    Pionowy pas oznacza niepewność DETEKCJI REAKCJI TERMICZNEJ,
    nie tolerancję faktycznego elektrycznego przełączenia grzałki.
    """
    events=r.heating_events
    if not events:
        return None
    ncol=2 if len(events)>1 else 1
    nrow=math.ceil(len(events)/ncol)
    fig,axs=plt.subplots(nrow,ncol,figsize=(15.4,4.0*nrow+1.3),squeeze=False)
    axs_flat=list(axs.flat)
    t=r.record.t
    for index,(ax,e) in enumerate(zip(axs_flat,events)):
        lo=max(t[0],e.time-200);hi=min(t[-1],e.time+280)
        left=bisect.bisect_left(t,lo);right=bisect.bisect_right(t,hi)
        time=[v/60 for v in t[left:right]]
        te=r.te[left:right];tc=r.tc[left:right]
        # Plot separately across measurement gaps
        xplot=list(time);ep=list(te);cp=list(tc)
        for j in range(1,len(time)):
            if t[left+j]-t[left+j-1] > 10:
                xplot.insert(j,float('nan'))
                ep.insert(j,float('nan'));cp.insert(j,float('nan'))
                break
        ax.plot(xplot,ep,color=COL['ev'],lw=2.0,label='Parownik')
        ax.plot(xplot,cp,color=COL['co'],lw=1.7,label='Skraplacz')
        if e.band_start is not None and e.band_end is not None:
            color = COL['ev'] if e.kind == 'HEATING_OFF_EST' else COL['co']
            ax.axvspan(e.band_start/60,e.band_end/60,color=color,alpha=.19,zorder=-1)
            ax.axvline(e.band_start/60,color=color,alpha=.7,ls=':',lw=1)
            ax.axvline(e.band_end/60,color=color,alpha=.7,ls=':',lw=1)
        if e.t_before is not None:
            ax.axhspan(e.t_before-1,e.t_before+1,color=COL['middle'],alpha=.15,zorder=-2)
            ax.axhline(e.t_before,color=COL['middle'],lw=1.2,ls='--',alpha=.85)
        ident='OFF?' if e.kind=='HEATING_OFF_EST' else 'P↑?' if e.kind=='HEATING_INCREASE_EST' else 'ON?'
        eventtext=f'{ident}: {e.time/60:.2f} min'
        if e.band_start is not None:
            eventtext+=f'  |  zakres: {e.band_start/60:.2f}–{e.band_end/60:.2f} min'
        ax.set_title(eventtext,fontsize=11,color='#293C4C')
        if e.method!='PLATEAU_PLUS_MINUS_1C':
            ax.text(.02,.96,'BRAK STABILNEGO PLATEAU — przybliżenie',ha='left',va='top',
                    fontsize=8.5,color='#935D26',transform=ax.transAxes,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.8))
        ax.set_ylabel('Temperatura [°C]')
        ax.set_xlabel('Czas rejestracji [min]')
        ax.grid(alpha=.21)
        ax.legend(loc='upper right',fontsize=8.5)
        ax.set_xlim(lo/60,hi/60)
    for ax in axs_flat[len(events):]:
        ax.axis('off')
    fig.suptitle(r.record.name + ' — zbliżenia reakcji ON?/OFF? (±1°C)',
                 fontsize=15,weight='bold',y=.995)
    fig.text(.5,.016,
             'Pas pionowy = przedział wykrycia reakcji temperatury, NIE czas przełączenia elektrycznego. '
             'Pas poziomy = stabilne T parownika ±1°C przed zmianą.',
             ha='center',fontsize=9,color='#586D80')
    fig.subplots_adjust(left=.075,right=.975,top=.88 if nrow==1 else .94,
                        bottom=.16 if nrow==1 else .09,hspace=.54,wspace=.18)
    path=directory / f'{safe_name(Path(r.record.name).stem)}_ONOFF_zblizenia.png'
    fig.savefig(path,dpi=145,facecolor='white')
    plt.close(fig)
    return path

def write_png(r: Analysis, directory: Path, *, bottom_values=None,
              bottom_label=None, bottom_level_one=False):
    base = safe_name(Path(r.record.name).stem)
    general = directory / f'{base}_analiza.png'
    make_plot_png(r, general, bottom_values=bottom_values,
                  bottom_label=bottom_label, bottom_level_one=bottom_level_one)
    zoom = []
    for ep in r.episodes:
        if not ep.oscillatory:
            continue
        p = directory / f'{base}_{ep.display_id}_zblizenie.png'
        make_plot_png(r, p, ep.start - 300, ep.end + 300,
                      bottom_values=bottom_values, bottom_label=bottom_label,
                      bottom_level_one=bottom_level_one)
        zoom.append(p)
    return general, zoom


def render_html(analyses, summaries, events, plot_index, ignored, bad,
                *, desktop_mode=False, panel_label=None, methodology_html=''):
    st='''<style>
    :root{font-family:Segoe UI,Arial,sans-serif;color:#203448;background:#f5f7fa}
    body{max-width:1450px;margin:0 auto;padding:32px 22px;line-height:1.53}
    h1{font-size:31px;margin-bottom:4px}h2{margin-top:36px}
    .sub{color:#607487}.panel{background:white;padding:22px;margin-top:18px;border-radius:13px;box-shadow:0 2px 10px #2233440c}
    table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px 10px;border-bottom:1px solid #e8edf1;text-align:left;vertical-align:top}
    th{background:#eaf0f5;color:#243f54;position:sticky;top:0}tr:hover td{background:#f6fafc}
    .scroll{overflow-x:auto}a{color:#146eab} .ok{color:#0a826a;font-weight:600}.warn{color:#aa7224;font-weight:600}
    .muted{color:#62778a;font-size:13px} img{display:block;max-width:100%;height:auto;border:1px solid #e0e8ee;border-radius:7px}
    code{background:#edf3f7;padding:2px 5px;border-radius:3px} ul{padding-left:24px}
    </style>'''
    def cell(x):return xml(x if x is not None else '')
    statuscol={'OSC_PLUS_POPRAWA_DELTAT':'ok','OSC_BEZ_POTWIERDZONEJ_POPRAWY':'warn'}
    out=['<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>PHP Analyzer – Results</title>',st,'</head><body>',
         '<h1>PHP Analyzer — raport pomiarów</h1>',
         f'<p class="sub">Wygenerowano: {xml(_dt.datetime.now().strftime("%Y-%m-%d %H:%M"))} · 3D PHP z pustym pojemnikiem · analiza sygnałów termicznych</p>',
         '<section class="panel"><h2>Podsumowanie</h2>',
         f'<p>Odczytano <b>{len(analyses)}</b> pomiarów CSV, wykryto <b>{len(events)}</b> zdarzeń termicznych. '
         'Na wykresach O1, O2… to epizody oscylacyjne; ON?/OFF? to przybliżone przejścia cieplne.</p>',
         '<p class="muted">Wykrycie aktywności termicznej jest przesłanką, nie bezpośrednim potwierdzeniem przepływu czynnika. '
         'Przed porównaniem pomiarów sprawdź zmiany mocy grzałki i warunków chłodzenia.</p>',
         '<p><a href="podsumowanie_testow.csv">Podsumowanie CSV</a> · '
         '<a href="wszystkie_epizody.csv">Oscylacje CSV</a> · <a href="wszystkie_zdarzenia_termiczne.csv">Wszystkie zdarzenia termiczne</a> · <a href="zmiany_grzania.csv">Szacowane ON/OFF</a> · <a href="luki_rejestracji.csv">Luki rejestracji</a></p>',
         '<div class="scroll"><table><thead><tr><th>Pomiar</th><th>Próbki</th><th>Czas [min]</th><th>Te max [°C]</th><th>ΔT max [K]</th><th>Epizody</th><th>Oscylacje</th><th>K1+K2</th><th>Interpretacja</th></tr></thead><tbody>']
    for row in summaries:
        name=row['plik']; loc=plot_index[name][0]
        vals=[row['liczba_probek'],row['czas_pomiaru_min'],row['T_parownik_max_C'],row['DeltaT_max_K'],row['liczba_zdarzen'],row['liczba_epizodow_oscylacyjnych'],row['oscylacje_plus_poprawa_DeltaT']]
        out.append('<tr><td><a href="#'+xml(safe_name(name))+'">'+xml(name)+'</a>'+(' <span class="muted">[fragment]</span>' if row['fragment_innego_pliku'] else '')+'</td>'+
                   ''.join('<td>'+cell(x)+'</td>' for x in vals)+f'<td class="{statuscol.get(row["status"],"")}">{cell(row["status"])}</td></tr>')
    out+=['</tbody></table></div></section>']
    out+=['<section class="panel"><h2>Legenda wyników</h2><ul>',
          '<li><b>Zielony:</b> oscylacje obu kanałów parownika + ≥15% redukcji ΔT przez ≥5 min w porównaniu z bazą lokalną.</li>',
          '<li><b>Pomarańczowy:</b> oscylacje temperatur bez potwierdzonej poprawy ΔT.</li>',
          '<li><b>ON?/OFF?:</b> szacowane przejścia cieplne. Kolorowe wąskie pasma obejmują zakres wykrycia zmiany o 1°C względem stabilnego poziomu przed zdarzeniem. <b>P↑?:</b> możliwy wzrost obciążenia. Nie są to przedziały potwierdzonego elektrycznego przełączenia grzałki.</li>',
          ('<li><b>Panel dolny eksportowanych PNG:</b> '+xml(panel_label)+'. '
           'Wartości wynikają z bieżącego Q i wybranej metryki, nie z proxy, '
           'chyba że jawnie wybrano proxy.</li>'
           if desktop_mode else
           '<li><b>Panel dolny:</b> ΔT/ΔT_ref jest tylko wskaźnikiem względnym. Przy stałej mocy R_app/R_ref = ΔT/ΔT_ref. Poziom odniesienia ustalono z pomiarów danego oszacowanego cyklu grzania; to nie jest R w K/W. Puste obszary oznaczają brak warunków do normalizacji, np. studzenie.</li>'),
          ('<li><b>RMS:</b> wykorzystywany w K1; można go wybrać jako trzeci panel.</li>'
           if desktop_mode else
           '<li><b>RMS:</b> nadal służy do detekcji oscylacji K1 i jest zapisywane w CSV; aby pokazać je na panelu dolnym, ustaw BOTTOM_PANEL = &quot;RMS&quot; w pliku .py.</li>'),
          '<li><b>Szare pasmo „BRAK DANYCH”:</b> brak rejestracji. Brak ciągłości pomiaru; nie interpretować okresu wewnątrz pasma jako pracy lub studzenia PHP.</li>',
          '</ul><p class="muted">Lokalna baza ΔT: okno od 6 do 1 minuty przed zdarzeniem. '
          'Progi mają charakter roboczy, wymagają walidacji; bez zsynchronizowanego logu mocy nie można potwierdzić K0.</p></section>']
    byfile={}
    for e in events:
        if e['status']!='THERMAL_TRANSIENT':
            byfile.setdefault(e['plik'],[]).append(e)
    for r in analyses:
        name=r.record.name; png,zooms,onoff_plot=plot_index[name]
        out+=['<section class="panel" id="'+xml(safe_name(name))+'">',
              '<h2>'+xml(name)+'</h2>',
              '<p class="muted">Źródło: '+xml(r.record.origin)+'</p>',
              '<p><a href="'+xml(png)+'">Otwórz wykres PNG</a> · '+
              ('<a href="'+xml(safe_name(Path(name).stem))+'/moc_i_opor.csv">Q i R CSV</a> · '
               '<a href="'+xml(safe_name(Path(name).stem))+'/przebieg_analityczny.csv">Przebieg liczbowy CSV</a> · '
               '<a href="'+xml(safe_name(Path(name).stem))+'/konfiguracja.json">Konfiguracja JSON</a></p>'
               if desktop_mode else
               '<a href="przebiegi/'+xml(safe_name(Path(name).stem))+'_przebieg.csv">Przebieg liczbowy CSV</a></p>'),
              '<img src="'+xml(png)+'" alt="Wykres '+xml(name)+'">']
        if onoff_plot:
            out.append('<p><a href="'+xml(onoff_plot)+'">Zbliżenia przedziałów ON?/OFF? — PNG</a></p>')
        if r.heating_events:
            out.append('<h3>Przedziały reakcji termicznej ON?/OFF? (nie przełączeń elektrycznych)</h3><div class="scroll"><table><tr><th>Zmiana</th><th>Reakcja [min]</th><th>Zakres [min]</th><th>Te przed [°C]</th><th>Te po [°C]</th><th>Metoda</th></tr>')
            for h in r.heating_events:
                typ='ON?' if h.kind=='HEATING_ON_EST' else 'OFF?' if h.kind=='HEATING_OFF_EST' else 'P↑?'
                method='poziom stabilny +-1°C' if h.method=='PLATEAU_PLUS_MINUS_1C' else 'orientacyjnie (brak stabilnego poziomu)'
                btxt=(fmt(h.band_start/60,2)+'–'+fmt(h.band_end/60,2)) if h.band_start is not None else '—'
                out.append('<tr><td>'+typ+'</td><td>'+fmt(h.time/60)+'</td><td>'+btxt+'</td><td>'+fmt(h.t_before)+'</td><td>'+fmt(h.t_after)+'</td><td>'+method+'</td></tr>')
            out.append('</table></div>')
        if byfile.get(name):
            out.append('<h3>Epizody oscylacyjne O1, O2…</h3><div class="scroll"><table><tr><th>Nr</th><th>Od [min]</th><th>Do [min]</th><th>Czas [min]</th><th>Od ON? [min]</th><th>Redukcja ΔT [%]</th><th>Ocena</th><th>PNG</th></tr>')
            for e in byfile[name]:
                ident=e['epizod']
                vals=[ident,e['poczatek_min_od_csv'],e['koniec_min_od_csv'],e['czas_trwania_min'],e['czas_od_szacowanego_ON_min'],e['redukcja_DeltaT_pct'],e['status']]
                matching=next((z for z in zooms if '_'+ident+'_zblizenie.png' in z),'')
                out.append('<tr>'+''.join('<td>'+cell(x)+'</td>' for x in vals)+
                           '<td>'+('<a href="'+xml(matching)+'">Powiększ</a>' if matching else '')+'</td></tr>')
            out.append('</table></div>')
        else:
            out.append('<p class="muted">Nie znaleziono powtarzalnych epizodów oscylacji spełniających robocze kryterium K1.</p>')
        trans=[ep for ep in r.episodes if not ep.oscillatory]
        if trans:
            out.append('<details><summary>Pozostałe przejścia termiczne — '+str(len(trans))+' (techniczne, bez oznaczeń na wykresie)</summary>')
            out.append('<p class="muted">Zmiana temperatury lub sygnał RMS, ale brak wymaganej serii oscylacji. Możliwy wpływ zmian mocy.</p><div class="scroll"><table><tr><th>ID</th><th>Od [min]</th><th>Do [min]</th><th>ΔT w zdarzeniu [K]</th></tr>')
            for ep in trans:
                out.append('<tr><td>'+ep.display_id+'</td><td>'+fmt(ep.start/60)+'</td><td>'+fmt(ep.end/60)+'</td><td>'+fmt(ep.median_delta)+'</td></tr>')
            out.append('</table></div></details>')
        out.append('<p class="muted">'+xml(' · '.join(r.notes))+'</p></section>')
    if ignored or bad:
        out+=['<section class="panel"><h2>Inne pliki / ostrzeżenia</h2><ul>']
        for item in ignored+bad:out.append('<li>'+xml(item)+'</li>')
        out.append('</ul></section>')
    if methodology_html:
        out.append('<p><a href="Metodyka_obliczen.html">Oddzielna strona metodyki obliczeń</a></p>')
        out.append(methodology_html)
    out.append('</body></html>')
    return '\n'.join(out)


def main() -> int:
    folder=Path(__file__).resolve().parent
    out=folder/'Results'
    plots=out/'wykresy'
    processed=out/'przebiegi'
    plots.mkdir(parents=True,exist_ok=True)
    processed.mkdir(parents=True,exist_ok=True)
    # Usuwamy wyłącznie stare zbliżenia generowane przez poprzedni skrypt,
    # inaczej w Results pozostaną E1..E9 pomimo nowego schematu O1..O2.
    for old in plots.glob('*_E*_zblizenie.png'):
        old.unlink()
    for old in plots.glob('*_O*_zblizenie.png'):
        old.unlink()
    # Starsze wersje eksportowały również SVG; zostawiamy tylko aktualne PNG.
    for old in plots.glob('*_analiza.svg'):
        old.unlink()
    for old in plots.glob('*_E*_zblizenie.svg'):
        old.unlink()
    print('PHP ANALYZER — ANALIZA FOLDERU')
    print('Folder źródłowy:',folder)
    items,ignored=find_inputs(folder)
    if not items:
        note=('Nie znaleziono plików CSV. Umieść plik php_analyzer.py w katalogu '\
             'z wyeksportowanymi pomiarami PicoLog (*.csv) lub archiwum ZIP zawierającym CSV.\n'\
             'Binarnych plików *.picolog program nie dekoduje.')
        (out/'INFORMACJA.txt').write_text(note,encoding='utf-8')
        print(note)
        return 1
    records,bad=unique_records(items)
    if not records:
        print('Nie odczytano poprawnych pomiarów:', '\n'.join(bad))
        (out/'BLEDY.txt').write_text('\n'.join(bad),encoding='utf-8')
        return 1
    analyses=[];plot_index={}
    for index,rec in enumerate(records,1):
        print(f'[{index}/{len(records)}] {rec.name}...',flush=True)
        try:
            r=analyze(rec)
            analyses.append(r)
            general,zooms=write_png(r,plots)
            onoff_png=make_heating_diagnostics(r,plots)
            export_series(r,processed/f'{safe_name(Path(rec.name).stem)}_przebieg.csv')
            plot_index[rec.name]=('wykresy/'+general.name,
                                  ['wykresy/'+z.name for z in zooms],
                                  'wykresy/'+onoff_png.name if onoff_png else None)
            print(f'   Zdarzenia: {len(r.episodes)}, oscylacje: {sum(x.oscillatory for x in r.episodes)}, '
                  f'oscylacje+K2: {sum(x.k2 for x in r.episodes)}')
        except Exception as exc:
            bad.append(f'Błąd analizy {rec.name}: {exc}\n{traceback.format_exc()}')
            print('   BŁĄD:',exc)
    if not analyses:
        (out/'BLEDY.txt').write_text('\n'.join(bad),encoding='utf-8')
        return 1
    summaries=csv_summary(analyses)
    episodes=csv_episodes(analyses)
    osc_episodes=[e for e in episodes if e['powtarzajace_sie_oscylacje']]
    heat_rows=csv_heating_events(analyses)
    gap_rows=csv_gaps(analyses)
    gap_fields=['plik','fragment_innego_pliku','ostatnia_probka_przed_luka_min',
                'pierwsza_probka_po_luce_min','czas_bez_danych_s','uwaga']
    write_csv(out/'luki_rejestracji.csv',gap_rows,gap_fields)
    write_csv(out/'podsumowanie_testow.csv',summaries,list(summaries[0]))
    # Always write episode CSV, even when no episodes were detected.
    episode_fields=['plik','epizod','fragment_innego_pliku','status','powtarzajace_sie_oscylacje',
       'wspolna_poprawa_DeltaT_K2','poczatek_min_od_csv','koniec_min_od_csv','czas_trwania_min',
       'liczba_maksimow','liczba_minimow','T_parownik_mediana_C','T_srodek_mediana_C',
       'T_skraplacz_mediana_C','DeltaT_przed_epizodem_K','DeltaT_w_epizodzie_K',
       'redukcja_DeltaT_pct','K2_laczny_czas_min','RMS_maks_C','korelacja_parownika']
    episode_fields.insert(episode_fields.index('czas_trwania_min')+1, 'czas_od_szacowanego_ON_min')
    write_csv(out/'wszystkie_epizody.csv',osc_episodes,episode_fields)
    write_csv(out/'wszystkie_zdarzenia_termiczne.csv',episodes,episode_fields)
    heater_fields=['plik','fragment_innego_pliku','rodzaj_zdarzenia',
                   'czas_od_poczatku_CSV_min','T_parownik_w_zdarzeniu_C',
                   'T_skraplacz_w_zdarzeniu_C','zmiana_parownik_4min_C',
                   'zmiana_skraplacz_4min_C','przedzial_od_min','przedzial_do_min',
                   'T_parownik_plateau_przed_C','T_parownik_plateau_po_C',
                   'metoda_przedzialu','interpretacja']
    write_csv(out/'zmiany_grzania.csv',heat_rows,heater_fields)
    (out/'Raport.html').write_text(render_html(analyses,summaries,episodes,plot_index,ignored,bad),encoding='utf-8')
    (out/'INFORMACJA.txt').write_text(
        'PHP Analyzer — wyniki\n\n'
        'Raport.html — otwórz w dowolnej przeglądarce.\n'
        'podsumowanie_testow.csv — jedna linia na plik.\n'
        'wszystkie_epizody.csv — tylko epizody oscylacji O1, O2...\n'
        'wszystkie_zdarzenia_termiczne.csv — także zdarzenia nieoscylacyjne T1, T2...\n'
        'zmiany_grzania.csv — przedziały reakcji +-1 C, NIE stan elektryczny.\n'
        'luki_rejestracji.csv — rzeczywiste przerwy w próbkowaniu.\n'
        'wykresy/ — PNG testów, oscylacji O1/O2 i zbliżeń ONOFF.\n'
        'przebiegi/ — temperatury, ΔT, RMS i względny wskaźnik R (proxy) w CSV (co 5 s).\n\n'
        'Dolny panel domyślnie pokazuje ΔT/ΔT_ref w rozpoznanych okresach grzania.\n'
        'Jest to R_app/R_ref wyłącznie przy niezmienionej mocy. Nie podajemy R [K/W].\n'
        'W kodzie BOTTOM_PANEL = RMS pozwala przywrócić wykres aktywności.\n\n'
        'Założenia: ch1,3 parownik; ch4,5 środek; ch6,7 skraplacz.\n'
        'Moc nie jest znana; ON?/OFF? jest tylko estymowane z temperatur.\n'
        'Wyniki detekcji nie są dowodem przepływu wewnątrz PHP.\n'
        'Format .picolog wymaga eksportu CSV w aplikacji PicoLog.\n',
        encoding='utf-8')
    if ignored or bad:
        (out/'LOG_OSTRZEZEN.txt').write_text('\n'.join(ignored+bad),encoding='utf-8')
    print('\nGOTOWE. Folder:',out)
    print(f'Plików: {len(analyses)}; zdarzeń termicznych: {len(episodes)}; '
          f'oscylacji: {sum(x.oscillatory for r in analyses for x in r.episodes)}')
    print('Otwórz Results/Raport.html')
    return 0


if __name__=='__main__':
    try:
        code=main()
    except Exception:
        print(traceback.format_exc())
        code=1
    if os.name=='nt' and sys.stdin.isatty():
        try:input('\nNaciśnij Enter, aby zamknąć...')
        except EOFError:pass
    sys.exit(code)
