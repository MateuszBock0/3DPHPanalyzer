"""Explainable, conservative thermal evidence of possible PHP activity.

This is NOT a detector of fluid motion. It combines already identified wall
temperature oscillations with independent section-temperature response and
operator-provided electrical/cooling assumptions. No score is a probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from math import isfinite, isclose
import php_analyzer as engine
from episode_validation import stable_positive_power

# Working, deliberately modest thermal-effect thresholds [°C].
# Both the thresholds and the baseline window require lab validation.
MIN_EVAPORATOR_DROP_C = 1.0
MIN_CONDENSER_RISE_C = 0.5
MIN_BASELINE_SPAN_S = 90.0


@dataclass(frozen=True)
class ActivityAssessment:
    code: str
    label: str
    dte_c: float | None
    dtc_c: float | None
    ddelta_k: float | None
    power_source: str
    power_w: float | None
    summary: str
    to_enter: str


def _median_samples(time, values, lo, hi, minimum_span=0):
    ids = [i for i, t in enumerate(time) if lo <= t <= hi and isfinite(values[i])]
    if len(ids) < 5 or time[ids[-1]]-time[ids[0]] < minimum_span:
        return None
    return median(values[i] for i in ids)


def _sensor_jump(analysis, lo, hi):
    time = analysis.record.t
    values = analysis.record.values
    steps = [b-a for a,b in zip(time,time[1:]) if b > a]
    sample_dt = median(steps) if steps else 1.0
    cutoff = max(10.0, 5.0*sample_dt)
    for i in range(1,len(time)):
        if time[i] < lo or time[i-1] > hi or time[i]-time[i-1] > cutoff:
            continue
        if any(abs(values[i][ch]-values[i-1][ch]) > 5.0 for ch in (0,1,4,5)):
            return True
    return False


def assess_episode(analysis, ep, resolved_stages, manual_stages=(),
                   constant_q=None, constant_scope='estimated',
                   cooling_confirmed=False):
    """Assess one oscillatory episode with explicit assumptions and blockers.

    The active median uses [start+30s, min(start+10min, end)]; the reference
    uses [start-6min, start-1min], matching the K2 baseline definition.
    Missing data are never joined across a logger gap.
    """
    if not ep.oscillatory:
        raise ValueError('Tylko epizody oscylacyjne O1/O2 można oceniać.')
    time=analysis.record.t
    origin=time[0]
    lo=max(time[0], ep.start-engine.PRE_BASELINE_START_S)
    hi=ep.start-engine.PRE_BASELINE_END_S
    active_lo=min(ep.end, ep.start+30.0)
    active_hi=min(ep.end, ep.start+600.0)
    gaps=engine.recording_segments(time)[1]
    interrupted=any(a < ep.end and b > lo for a,b in gaps)
    if interrupted:
        before_e=before_c=after_e=after_c=None
    else:
        before_e=_median_samples(time,analysis.te,lo,hi,MIN_BASELINE_SPAN_S)
        before_c=_median_samples(time,analysis.tc,lo,hi,MIN_BASELINE_SPAN_S)
        after_e=_median_samples(time,analysis.te,active_lo,active_hi,30)
        after_c=_median_samples(time,analysis.tc,active_lo,active_hi,30)
    valid=all(x is not None for x in (before_e,before_c,after_e,after_c))
    dte=after_e-before_e if valid else None
    dtc=after_c-before_c if valid else None
    ddelta=dte-dtc if valid else None
    opposite=valid and dte <= -MIN_EVAPORATOR_DROP_C and dtc >= MIN_CONDENSER_RISE_C
    jumps=_sensor_jump(analysis,lo,ep.end)
    qa,q_reason=stable_positive_power(resolved_stages,
                      (lo-origin)/60,(ep.end-origin)/60)
    # An inferred thermal ON? is NOT electrically verified Q(t).
    manual_q=stable_positive_power(manual_stages,(lo-origin)/60,(ep.end-origin)/60)[0]
    manually_covered=(qa is not None and manual_q is not None
                      and isclose(qa,manual_q,rel_tol=0,abs_tol=1e-9))
    declared_full=qa is not None and constant_scope=='full' and constant_q is not None
    declared=manually_covered or declared_full
    power_source=('Q wpisana dla całego okna' if manually_covered else
                  'Q zadeklarowana dla pliku' if declared_full else
                  'Q przypisana wg ON?' if qa is not None else
                  'Q nieznana / zmienna / OFF')
    reasons=['K1: powtarzalne oscylacje obu termopar parownika']
    if valid:
        reasons.append(f'Zmiana względem okresu przed O: ΔTe={dte:+.2f}°C, ΔTc={dtc:+.2f}°C, Δ(Te−Tc)={ddelta:+.2f} K')
        reasons.append('Te maleje i Tc rośnie' if opposite else
                       'Brak jednoczesnego potwierdzenia spadku Te i wzrostu Tc')
    else:
        reasons.append('Brak ciągłego lub wystarczającego okna porównania temperatur')
    reasons.append('K2 termiczne spełnione' if ep.k2 else 'K2 termiczne niespełnione')
    reasons.append(power_source + (f' ({qa:g} W)' if qa is not None else ''))
    if jumps: reasons.append('Skok >5°C między sąsiednimi próbkami: sprawdź czujniki')
    if interrupted: reasons.append('Luka rejestracji w oknie porównania')
    if qa is None: reasons.append(q_reason)
    if not cooling_confirmed: reasons.append('Warunki chłodzenia niepotwierdzone przez operatora')

    needs=[]
    if not declared:
        needs.append('Wpisz rzeczywiste Q i czasy zmian mocy (nie tylko szacowane ON?)')
    if not cooling_confirmed:
        needs.append('Potwierdź porównywalne chłodzenie z dziennika')
    if not valid:
        needs.append('Sprawdź czy są co najmniej 90 s danych przed epizodem')
    if jumps:
        needs.append('Zweryfikuj skoki termopar')
    if declared and qa is not None and cooling_confirmed and opposite and ep.k2 and not jumps and not interrupted:
        code='SILNE_PRZESLANKI'
        label='Silne przesłanki aktywności'
    elif qa is None and resolved_stages and not q_reason.startswith('Q nieznana'):
        # A known OFF or power change could explain the thermal signal.
        code='NIEJEDNOZNACZNE'
        label='Niejednoznaczne: Q/OFF'
    elif interrupted or jumps:
        code='NIEJEDNOZNACZNE'
        label='Niejednoznaczne: dane/czujniki'
    elif opposite or ep.k2:
        code='MOZLIWA_AKTYWNOSC'
        label='Możliwa aktywność PHP'
    else:
        code='NIEJEDNOZNACZNE'
        label='Oscylacje; brak zgodnych przesłanek'
    return ActivityAssessment(code,label,dte,dtc,ddelta,power_source,qa,
                              '; '.join(reasons)+'. Bez bezpośredniego potwierdzenia ruchu czynnika.',
                              '; '.join(needs) if needs else
                              'Powtórz próbę; sprawdź ręczne notatki Q, chwile przełączeń i warunki chłodzenia')


def assess_all(analysis, resolved_stages, manual_stages=(), constant_q=None,
               constant_scope='estimated', cooling_confirmed=False):
    return {ep.display_id: assess_episode(
        analysis, ep, resolved_stages, manual_stages, constant_q,
        constant_scope, cooling_confirmed)
        for ep in analysis.episodes if ep.oscillatory}
