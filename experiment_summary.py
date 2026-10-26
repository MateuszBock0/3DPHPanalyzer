"""Per-experiment overview from existing thermal analysis and operator Q model.

A dashboard is a presentation of evidence, not a second PHP detector.
All temperatures and Q are inherited from the current record and calculations.
No U/I is measured; dates of heater switching are not inferred from Q.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median

from episode_validation import stable_positive_power


@dataclass(frozen=True)
class EpisodeSummary:
    ident: str
    start_min: float
    end_min: float
    duration_min: float
    delta_before_k: float | None
    delta_during_k: float
    reduction_pct: float | None
    k2_thermal: bool
    k2_label: str
    activity_label: str


@dataclass(frozen=True)
class ExperimentSummary:
    filename: str
    duration_min: float
    count: int
    first_id: str | None
    first_min: float | None
    first_from_on_min: float | None
    on_provenance: str
    q_display: str
    q_detail: str
    delta_display: str
    delta_detail: str
    r_display: str
    r_detail: str
    cooling_confirmed: bool
    episodes: tuple[EpisodeSummary, ...]


def _startup_anchor(row, first_start_min):
    """Use an ON only if no later OFF cancels it before the first O1.

    Electrical entries from the operator have precedence. A temperature
    response ON? can only supply an *approximate* offset. The CSV start,
    constant-Q declaration and manually drawn Q stages are never ON markers.
    """
    events = sorted((ev for ev in row.get('timeline_events', [])
                     if ev.time_min <= first_start_min),
                    key=lambda ev: ev.time_min)
    anchor = None
    origin = None
    for ev in events:
        if ev.kind == 'OFF':
            anchor = origin = None
        elif ev.kind == 'ON':
            anchor = ev.time_min
            origin = ('ON wpisany przez operatora' if ev.source == 'operator'
                      else 'ON? z zaakceptowanej sugestii termicznej')
    if anchor is not None:
        return first_start_min-anchor, origin
    # If the operator explicitly registered an OFF and no later ON,
    # do not silently resurrect a guessed thermal start.
    if any(ev.kind == 'OFF' for ev in events):
        return None, 'Brak ON po ostatnim ręcznym OFF'
    suggestions = sorted((s for s in row.get('thermal_suggestions', [])
                          if s.time_min <= first_start_min),
                         key=lambda s: s.time_min)
    guess = None
    for suggestion in suggestions:
        if suggestion.kind == 'HEATING_ON_EST':
            guess = suggestion.time_min
        elif suggestion.kind == 'HEATING_OFF_EST':
            guess = None
    if guess is None:
        return None, 'Nieznany początek grzania'
    return first_start_min-guess, 'Od ON? (reakcja cieplna, wyłącznie szacunek)'


def _q_overview(row):
    stages = row.get('effective_stages', [])
    positive = sorted(set(float(s.q_w) for s in stages if s.q_w > 0))
    has_zero = any(s.q_w == 0 for s in stages)
    duration = (row['record'].t[-1]-row['record'].t[0])/60
    covered = sum(s.end_min-s.start_min for s in stages)
    incomplete = covered < duration-1e-5
    if not positive:
        if has_zero:
            return 'Brak Q > 0', 'Znamy jedynie okresy OFF (Q=0 W); dla grzania Q nieznana.'
        return 'Q nieznana', 'Wprowadź nastawę grzałki Q [W] i chwile ON/OFF w zakładce Wykresy.'
    values = ' / '.join(f'{v:g}' for v in positive)
    name = f'{values} W' if len(positive) <= 2 else f'{len(positive)} poziomy Q'
    detail = ('Nastawa Q przypisana do okresów grzania; nie jest pomiarem U/I. '
              + ('Q pozostaje nieznana w części pomiaru.' if incomplete else
                 'Cały czas ma przypisany stan Q lub OFF.'))
    if len(positive)>1:
        detail += ' Moc zmieniała się; nie porównuj R_app między różnymi Q bez kontroli warunków.'
    return name, detail


def _r_in_first_episode(row, first):
    if first is None:
        return '—', 'Brak epizodu O1 do oceny R_app.'
    t0 = row['record'].t[0]
    a, b = (first.start-t0)/60, (first.end-t0)/60
    q, reason = stable_positive_power(row.get('effective_stages', []), a, b)
    if q is None:
        return '—', 'R_app dla O1 nieporównywalne: ' + reason + '.'
    values = [r for t, r in zip(row['record'].t, row['results']['r'])
              if first.start <= t <= first.end and r is not None and isfinite(r)]
    if not values:
        return '—', 'Brak prawidłowego R_app w O1 mimo przypisanej Q.'
    manual = any(s.start_min <= a+1e-7 and s.end_min >= b-1e-7
                 and abs(s.q_w-q)<1e-9
                 for s in row.get('stages', []))
    marker = any(ev.kind=='ON' and ev.source=='operator' and
                 ev.time_min <= a+1e-7 for ev in row.get('timeline_events', []))
    declared_full = row.get('constant_scope')=='full' and row.get('constant_q') is not None
    provenance = ('ręcznie wpisanej' if manual or marker or declared_full
                  else 'szacunkowo przypisanej')
    return (f'{median(values):.3g} K/W',
            f'Mediana przejściowego R_app w O1 przy Q={q:g} W '
            f'({provenance} nastawy). Nie jest to Rref ani stan ustalony.')


def build_experiment_summary(row):
    analysis = row['analysis']
    record = row['record']
    if not record.t:
        raise ValueError('Brak próbek czasu.')
    t0 = record.t[0]
    episodes = sorted((ep for ep in analysis.episodes if ep.oscillatory),
                      key=lambda ep: ep.start)
    first = episodes[0] if episodes else None
    details = []
    for ep in episodes:
        review = row.get('k2_reviews', {}).get(ep.display_id)
        activity = row.get('activity_assessments', {}).get(ep.display_id)
        details.append(EpisodeSummary(
            ep.display_id, (ep.start-t0)/60, (ep.end-t0)/60,
            (ep.end-ep.start)/60, ep.baseline, ep.median_delta,
            ep.reduction_pct, bool(ep.k2),
            review.label if review is not None else ('K2 termiczne' if ep.k2 else 'Tylko K1'),
            activity.label if activity is not None else 'Brak kwalifikacji'))
    if first is None:
        delta_display='—'
        delta_detail='Brak wykrytego O1; nie oznacza to braku przepływu czynnika.'
        first_from_on, origin=None,'Brak epizodu oscylacyjnego O1'
    else:
        if first.reduction_pct is None or not isfinite(first.reduction_pct):
            delta_display='—'
            delta_detail='Brak wiarygodnej lokalnej bazy ΔT przed O1.'
        else:
            delta_display=f'{first.reduction_pct:+.1f}%'
            delta_detail=(f'O1: mediana ΔT {first.median_delta:.2f} K, '
                          f'przed O1 {first.baseline:.2f} K. '
                          'Zmiana względem lokalnej bazy, nie względem początku CSV.')
            if first.reduction_pct < 0:
                delta_detail+=' Znak ujemny oznacza wzrost ΔT.'
        first_from_on, origin = _startup_anchor(row,(first.start-t0)/60)
    q_display, q_detail = _q_overview(row)
    r_display, r_detail = _r_in_first_episode(row,first)
    return ExperimentSummary(
        filename=record.name, duration_min=(record.t[-1]-t0)/60,
        count=len(episodes), first_id=first.display_id if first else None,
        first_min=(first.start-t0)/60 if first else None,
        first_from_on_min=first_from_on, on_provenance=origin,
        q_display=q_display, q_detail=q_detail,
        delta_display=delta_display, delta_detail=delta_detail,
        r_display=r_display, r_detail=r_detail,
        cooling_confirmed=bool(row.get('cooling_confirmed',False)),
        episodes=tuple(details))
