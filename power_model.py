"""Measured/heater-power schedule and defensible apparent thermal resistance.

No power is inferred from temperature. Unknown Q and Q=0 produce no R_app.
Time intervals are measured in minutes relative to the first CSV reading.
"""
from __future__ import annotations
from dataclasses import dataclass
from bisect import bisect_right
from statistics import median
from typing import Optional
import math


@dataclass(frozen=True)
class PowerStage:
    start_min: float
    end_min: float
    q_w: float


def validate(stages: list[PowerStage]) -> list[PowerStage]:
    ordered = sorted(stages, key=lambda x: x.start_min)
    for i, step in enumerate(ordered):
        if not all(math.isfinite(v) for v in (step.start_min, step.end_min, step.q_w)):
            raise ValueError('Etap mocy zawiera wartość nieliczbową.')
        if step.start_min < 0 or step.end_min <= step.start_min or step.q_w < 0:
            raise ValueError('Wymagane: 0 ≤ początek < koniec oraz Q ≥ 0 W.')
        if i and step.start_min < ordered[i-1].end_min - 1e-9:
            raise ValueError('Przedziały Q nie mogą na siebie zachodzić.')
    return ordered


@dataclass(frozen=True)
class EstimatedPeriod:
    """Thermal-response state only, NEVER electrically verified heater state."""
    start_min: float
    end_min: float
    state: str  # UNKNOWN / ON? / OFF? / P_UP? / GAP
    note: str = ''


def derive_estimated_periods(t_seconds, heating_events, gaps=()):
    """Partition the recording using inferred thermal changes and missing-data gaps.

    The result is a DRAFT for the operator. P_UP? is not a known power level.
    A gap terminates any inferred state: we cannot infer what happened while
    the data logger was offline. All times are minutes since first CSV sample.
    """
    if len(t_seconds) < 2:
        return []
    t0 = float(t_seconds[0])
    duration = (float(t_seconds[-1]) - t0) / 60
    if duration <= 0:
        return []
    changes = []
    known = {'HEATING_ON_EST': 'ON?', 'HEATING_OFF_EST': 'OFF?',
             'HEATING_INCREASE_EST': 'P_UP?'}
    for event in heating_events:
        state = known.get(event.kind)
        when = (float(event.time) - t0) / 60
        if state and 0 <= when <= duration:
            changes.append((when, 2, state))
    for start, end in gaps:
        a = max(0., (float(start) - t0) / 60)
        b = min(duration, (float(end) - t0) / 60)
        if b > a:
            changes.extend(((a, 0, 'GAP'), (b, 1, 'UNKNOWN')))
    # Events at a gap boundary are processed last; a subsequent ON? can
    # reinstate an inferred state, but gaps themselves never imply OFF?.
    changes.sort(key=lambda item: (item[0], item[1]))
    result = []
    last = 0.
    state = 'UNKNOWN'
    for current, _priority, next_state in changes:
        current = min(duration, max(0., current))
        if current - last > 1e-8:
            result.append(EstimatedPeriod(last, current, state,
                                         'Szacowany stan z temperatur' if state not in ('UNKNOWN', 'GAP')
                                         else 'Stan nieustalony / brak pomiaru'))
        state, last = next_state, current
    if duration - last > 1e-8:
        result.append(EstimatedPeriod(last, duration, state,
                                     'Koniec rejestracji, brak potwierdzenia elektrycznego'
                                     if state in ('ON?', 'P_UP?') else 'Szacowany stan z temperatur'))
    return result


def effective_stages(periods: list[EstimatedPeriod], constant_q: Optional[float],
                     overrides: list[PowerStage], duration: float,
                     scope: str = 'estimated') -> list[PowerStage]:
    """Resolve Q with priority manual override > optional constant-Q base.

    No constant Q -> no automatic assignment even for estimated OFF?.
    Scope 'estimated': ON? gets Q, OFF? gets 0 W, P_UP?/unknown/gap NULL.
    Scope 'full': user expressly assigns Q to the entire recorded time.
    Neither scope changes the origin or uncertainty of estimated periods.
    """
    ordered = validate(overrides)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError('Nieprawidłowy czas trwania pomiaru.')
    if scope not in ('estimated', 'full'):
        raise ValueError('Nieznany tryb stałej mocy Q.')
    if constant_q is not None and (not math.isfinite(constant_q) or constant_q < 0):
        raise ValueError('Stała moc Q musi być nieujemną liczbą w watach.')
    base = []
    if constant_q is not None:
        if scope == 'full':
            base = [PowerStage(0., duration, constant_q)] if duration else []
        else:
            for p in periods:
                power = (constant_q if p.state == 'ON?' else
                         0. if p.state == 'OFF?' else None)
                if power is not None and p.end_min > p.start_min:
                    base.append(PowerStage(p.start_min, p.end_min, power))
    # Split on all relevant boundaries; every subinterval has one source.
    boundaries = {0., duration}
    for stage in base + ordered:
        boundaries.add(max(0., min(duration, stage.start_min)))
        boundaries.add(max(0., min(duration, stage.end_min)))
    edges = sorted(boundaries)
    result = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 1e-8:
            continue
        x = (a + b) / 2
        manual = next((s for s in ordered if s.start_min <= x < s.end_min), None)
        auto = next((s for s in base if s.start_min <= x < s.end_min), None)
        chosen = manual if manual is not None else auto
        if chosen is None:
            continue
        power = chosen.q_w
        if result and abs(result[-1].end_min - a) < 1e-8 and result[-1].q_w == power:
            prev = result.pop()
            result.append(PowerStage(prev.start_min, b, power))
        else:
            result.append(PowerStage(a, b, power))
    return result


def calculate(t_seconds, delta_k, stages: list[PowerStage],
              ref_range_min: Optional[tuple[float, float]] = None,
              *, te=None, tc=None, max_ref_trend_c_min=0.5, min_ref_duration_s=120):
    """Return sampled Q, R_app [K/W], R/R_ref, and reference details.

    For normalization a single constant Q>0 must hold in the reference window;
    relative values are restricted to that same power level.
    """
    stages = validate(stages)
    if len(t_seconds) != len(delta_k):
        raise ValueError('Niepasujące długości sygnałów.')
    if (te is None) != (tc is None):
        raise ValueError('Sprawdzenie stabilności Rref wymaga równocześnie Te i Tc.')
    if te is not None and (len(te) != len(t_seconds) or len(tc) != len(t_seconds)):
        raise ValueError('Niepasujące długości temperatur dla Rref.')
    if max_ref_trend_c_min <= 0 or min_ref_duration_s <= 0:
        raise ValueError('Parametry kontroli stabilności Rref muszą być dodatnie.')
    boundaries = [s.start_min for s in stages]
    origin = float(t_seconds[0]) if t_seconds else 0.0
    q, rr_abs = [], []
    for t, delta in zip(t_seconds, delta_k):
        minute = (float(t) - origin) / 60.0
        j = bisect_right(boundaries, minute) - 1
        power = (stages[j].q_w if j >= 0 and minute < stages[j].end_min else None)
        q.append(power)
        rr_abs.append(delta / power if power is not None and power > 0 and math.isfinite(delta) else None)
    reference_r, reference_q, reference_error = None, None, None
    rr = [None] * len(q)
    if ref_range_min is not None:
        a, b = ref_range_min
        duration = (float(t_seconds[-1]) - origin) / 60 if t_seconds else 0.0
        if not all(math.isfinite(x) for x in (a, b)) or a < 0 or a >= b or b > duration + 1e-9:
            reference_error = 'Błędny przedział odniesienia (poza czasem rejestracji lub Od ≥ Do).'
        else:
            # Validate the entire [a,b) interval, not just samples with defined R.
            # Skipping OFF samples would admit 10W -> OFF -> 10W as one reference.
            eligible = [stage for stage in stages if stage.start_min <= a + 1e-9
                        and stage.end_min >= b - 1e-9 and stage.q_w > 0]
            if len(eligible) != 1:
                reference_error = ('R_ref: całe okno musi leżeć w JEDNYM ciągłym etapie '
                                   'stałej dodatniej Q (bez OFF i odcinków nieznanych).')
            else:
                target_q = eligible[0].q_w
                in_window = [i for i, t in enumerate(t_seconds)
                             if a <= (float(t)-origin)/60 < b]
                if len(in_window) < 5 or any(
                    q[i] is None or not math.isclose(q[i], target_q, rel_tol=0, abs_tol=1e-9)
                    or rr_abs[i] is None for i in in_window):
                    reference_error = 'R_ref wymaga co najmniej 5 poprawnych próbek przy stałej Q > 0.'
                else:
                    from statistics import median as _median
                    steps = [float(y)-float(x) for x, y in zip(t_seconds, t_seconds[1:]) if y > x]
                    threshold = max(10.0, 5.0 * (_median(steps) if steps else 1.0))
                    gap_inside = any(
                        float(y)-float(x) > threshold and
                        float(x) < origin+60*b and float(y) > origin+60*a
                        for x, y in zip(t_seconds, t_seconds[1:]))
                    if gap_inside:
                        reference_error = 'R_ref: okno odniesienia przecina lukę rejestracji danych.'
                    elif te is not None and (b-a)*60 < min_ref_duration_s - 1e-7:
                        reference_error = (
                            f'R_ref: okno quasi-ustalone musi trwać co najmniej {min_ref_duration_s:g} s.')
                    elif te is not None:
                        # Use medians of early/late quarters to limit the impact
                        # of individual sensor spikes. This is a WORKING screening
                        # criterion, not proof of physical steady state.
                        width=max(1,len(in_window)//4)
                        first,last=in_window[:width],in_window[-width:]
                        centre_first=_median([float(t_seconds[i]) for i in first])
                        centre_last=_median([float(t_seconds[i]) for i in last])
                        dt_minutes=(centre_last-centre_first)/60
                        if dt_minutes <= 0:
                            reference_error = 'R_ref: niewystarczający zakres czasu.'
                        else:
                            rates=[]
                            for signal in (te,tc):
                                samples=[signal[i] for i in first+last]
                                if any(not math.isfinite(z) for z in samples):
                                    reference_error='R_ref: niepoprawna temperatura.'
                                    break
                                rates.append(abs((_median([signal[i] for i in last])-
                                                  _median([signal[i] for i in first]))/dt_minutes))
                            if reference_error is None and max(rates)>max_ref_trend_c_min:
                                reference_error=(
                                    f'R_ref: trend Te/Tc {max(rates):.3f} °C/min przekracza '
                                    f'roboczy próg {max_ref_trend_c_min:g} °C/min.')
                    if reference_error is None:
                        reference_q = target_q
                        reference_r = _median([rr_abs[i] for i in in_window])
                        if not math.isfinite(reference_r) or abs(reference_r) <= 1e-12:
                            reference_error = 'R_ref zerowe lub nieokreślone.'
                            reference_r = reference_q = None
                        else:
                            rr = [r / reference_r if r is not None and power is not None
                                  and math.isclose(power, reference_q, abs_tol=1e-9, rel_tol=0)
                                  else None for r, power in zip(rr_abs, q)]
    return {'q': q, 'r': rr_abs, 'relative': rr, 'r_ref': reference_r,
            'q_ref': reference_q, 'reference_error': reference_error}
