"""Operator-assisted heater timeline for temperature-only PHP experiments.

The program NEVER infers numerical electrical power from wall temperatures.
Auto-detected ON?/OFF? timestamps remain thermal-response suggestions even
after the operator accepts them. Explicit edits are also user assumptions,
unless independently confirmed in a lab log.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from bisect import bisect_left
from types import SimpleNamespace
from power_model import PowerStage, effective_stages, validate


@dataclass(frozen=True)
class Transition:
    time_min: float
    kind: str  # ON, OFF, CHANGE_Q
    q_w: float | None = None
    source: str = 'operator'  # operator or accepted_thermal_estimate


def validate_transitions(transitions, duration_min):
    if not isfinite(duration_min) or duration_min <= 0:
        raise ValueError('Nieprawidłowy czas trwania rejestracji.')
    output = sorted(transitions, key=lambda event: event.time_min)
    for i, event in enumerate(output):
        if event.kind not in ('ON', 'OFF', 'CHANGE_Q'):
            raise ValueError('Nieznany rodzaj ręcznego zdarzenia.')
        if event.source not in ('operator', 'accepted_thermal_estimate'):
            raise ValueError('Nieznane pochodzenie znacznika.')
        # A confirmed OFF may sit exactly at the last recorded instant.
        # No other event may start a nonzero heating interval at this boundary.
        terminal_off = event.kind == 'OFF' and abs(event.time_min-duration_min) < 1e-8
        if not isfinite(event.time_min) or not (0 <= event.time_min < duration_min or terminal_off):
            raise ValueError('ON/Q musi poprzedzać koniec pomiaru. OFF może przypadać dokładnie na koniec CSV.')
        if event.kind == 'OFF':
            if event.q_w is not None and event.q_w != 0:
                raise ValueError('OFF musi oznaczać 0 W.')
        elif event.q_w is None or not isfinite(event.q_w) or event.q_w <= 0:
            raise ValueError('Dla ON i zmiany Q wpisz rzeczywistą moc większą od 0 W.')
        if i and event.time_min-output[i-1].time_min < 1e-6:
            raise ValueError('Dwa zdarzenia nie mogą mieć tego samego czasu.')
    return output


def timeline_stages(transitions, duration_min):
    """Operator transitions define Q from each marker until the next marker/end."""
    ordered = validate_transitions(transitions, duration_min) if transitions else []
    result = []
    for i, event in enumerate(ordered):
        end = ordered[i+1].time_min if i+1 < len(ordered) else duration_min
        # Terminal OFF closes the annotation, but has no measured duration.
        # Do not create a zero-length stage that would fail power validation.
        if end > event.time_min + 1e-9:
            result.append(PowerStage(event.time_min, end,
                                     0. if event.kind == 'OFF' else event.q_w))
    return result

def operator_marker_stages(transitions, duration_min):
    """Only explicitly placed operator markers count as user-entered Q evidence.

    A bulk-accepted thermal suggestion MUST NOT gain the provenance of a
    manually recorded electrical switch time merely by acceptance.
    """
    ordered = validate_transitions(transitions, duration_min) if transitions else []
    stages = timeline_stages(ordered, duration_min)
    return [stage for event, stage in zip(ordered, stages)
            if event.source == 'operator']


def overlay_stages(under, over, duration_min):
    """Overwrite known intervals only, preserving uncovered/unknown Q intervals."""
    validate(under)
    validate(over)
    boundaries = {0., duration_min}
    for item in list(under)+list(over):
        boundaries.add(max(0., min(duration_min, item.start_min)))
        boundaries.add(max(0., min(duration_min, item.end_min)))
    result = []
    for a, b in zip(sorted(boundaries), sorted(boundaries)[1:]):
        if b-a <= 1e-9:
            continue
        middle = (a+b)/2
        picked = next((s for s in over if s.start_min <= middle < s.end_min), None)
        if picked is None:
            picked = next((s for s in under if s.start_min <= middle < s.end_min), None)
        if picked is None:
            continue
        if result and abs(result[-1].end_min-a) < 1e-8 and result[-1].q_w == picked.q_w:
            last=result.pop()
            result.append(PowerStage(last.start_min,b,picked.q_w))
        else:
            result.append(PowerStage(a,b,picked.q_w))
    return result


def resolve_schedule(periods, constant_q, overrides, duration_min,
                     scope='estimated', transitions=()):
    """Precedence: explicit interval override > timeline marker > suggested Q."""
    base = effective_stages(periods,constant_q,[],duration_min,scope)
    manual = timeline_stages(transitions,duration_min)
    return overlay_stages(overlay_stages(base,manual,duration_min),
                          validate(list(overrides)),duration_min)


def proposals_from_thermal(heating_events, start_s, duration_min, operator_q):
    """Produce inspectable, unconfirmed thermal proposals, excluding P_UP?."""
    mapping = {'HEATING_ON_EST':'ON','HEATING_OFF_EST':'OFF'}
    events=[]
    for candidate in heating_events:
        kind=mapping.get(candidate.kind)
        if kind is None:
            continue
        minute=(float(candidate.time)-start_s)/60.
        if minute < 0 or minute >= duration_min:
            continue
        q = operator_q if kind=='ON' else 0.
        if kind=='ON' and (q is None or not isfinite(q) or q <= 0):
            raise ValueError('Podaj Q > 0 W dla zatwierdzanych sugestii ON?.')
        events.append(Transition(minute,kind,q,'accepted_thermal_estimate'))
    return validate_transitions(events,duration_min) if events else []


def snap_to_recorded_sample(minutes, seconds, *, max_offset_s=35.):
    """Reject clicks inside long logger gaps; find nearest actually observed time."""
    if not seconds:
        raise ValueError('Brak zarejestrowanych próbek.')
    target=seconds[0]+60*minutes
    j=bisect_left(seconds,target)
    step=median((b-a for a,b in zip(seconds,seconds[1:]) if b>a)) if len(seconds)>1 else 1.
    gap_threshold=max(10.0,5.0*step)
    if 0 < j < len(seconds) and seconds[j-1] < target < seconds[j] and (
            seconds[j]-seconds[j-1] > gap_threshold):
        raise ValueError('Kliknięto w lukę rejestracji; nie można określić czasu ON/OFF bez danych.')
    candidates=[seconds[i] for i in (j-1,j) if 0 <= i < len(seconds)]
    chosen=min(candidates,key=lambda t:abs(t-target))
    tolerance=max(max_offset_s,2.5*step)
    if abs(target-chosen)>tolerance:
        raise ValueError('Kliknięto w lukę rejestracji, bez pobliskiej próbki. Wybierz czas z dostępnymi pomiarami.')
    return (chosen-seconds[0])/60.


def last_heating_boundary(transitions, duration_min):
    """Describe the closing edge without inventing an electrical OFF.

    Returns (time_min, text, electrically_confirmed_by_operator).
    No transition means a data boundary, not evidence of heater shutoff.
    """
    ordered = validate_transitions(transitions, duration_min) if transitions else []
    if ordered and ordered[-1].kind == 'OFF':
        label = ('OFF (wpis operatora)' if ordered[-1].source == 'operator'
                 else 'OFF? (zaakceptowana sugestia termiczna)')
        return ordered[-1].time_min, label, ordered[-1].source == 'operator'
    return duration_min, 'KONIEC CSV — OFF niepotwierdzone', False


@dataclass(frozen=True)
class ThermalSuggestion:
    """Editable temperature-response boundary, not an electrical switch."""
    time_min: float
    kind: str  # HEATING_ON_EST / HEATING_OFF_EST / HEATING_INCREASE_EST
    source: str = 'automatic'  # automatic / operator_adjusted / operator_added


SUGGESTION_KINDS = frozenset(('HEATING_ON_EST', 'HEATING_OFF_EST', 'HEATING_INCREASE_EST'))
SUGGESTION_SOURCES = frozenset(('automatic', 'operator_adjusted', 'operator_added'))


def validate_suggestions(suggestions, duration_min):
    if not isfinite(duration_min) or duration_min <= 0:
        raise ValueError('Nieprawidłowy czas pomiaru.')
    ordered=sorted(suggestions,key=lambda s:s.time_min)
    for i, marker in enumerate(ordered):
        if marker.kind not in SUGGESTION_KINDS or marker.source not in SUGGESTION_SOURCES:
            raise ValueError('Niepoprawny typ lub pochodzenie sugestii termicznej.')
        if not isfinite(marker.time_min) or marker.time_min < 0 or marker.time_min > duration_min:
            raise ValueError('Sugestia ON?/OFF? musi leżeć w granicach pomiaru.')
        if i and marker.time_min-ordered[i-1].time_min < 1e-6:
            raise ValueError('Dwie sugestie nie mogą znajdować się w identycznym czasie.')
    return ordered


def initial_suggestions(heating_events, first_s, duration_min):
    return validate_suggestions([
        ThermalSuggestion((float(e.time)-first_s)/60, e.kind)
        for e in heating_events if e.kind in SUGGESTION_KINDS
    ], duration_min)


def suggested_heating_events(suggestions, origin_s):
    """Only for deriving provisional ON?/OFF?/P_UP? periods; leaves K1/K2 raw events intact."""
    return [SimpleNamespace(kind=s.kind,time=origin_s+60*s.time_min)
            for s in suggestions]
