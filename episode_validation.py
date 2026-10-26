"""Post-hoc scientific qualification of thermal K2 and final resolved Q.

K2 thermal detection in php_analyzer.py is kept unchanged for backward
compatibility. This module qualifies its interpretation after operator Q
and cooling-conditions declarations are known. No claim of fluid motion.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import php_analyzer as engine


@dataclass(frozen=True)
class K2Review:
    code: str
    label: str
    explanation: str
    q_w: float | None = None


def resolved_q_label(stages, begin_min, end_min):
    """Describe FINAL resolved Q over the whole inferred period, not base Q."""
    if end_min <= begin_min:
        return '—'
    eps = 1e-7
    clipped = [(max(begin_min, s.start_min), min(end_min, s.end_min), s.q_w)
               for s in stages if s.start_min < end_min - eps and s.end_min > begin_min + eps]
    clipped = sorted((a, b, q) for a, b, q in clipped if b > a + eps)
    if not clipped:
        return 'Q nieznana'
    covered = begin_min
    missing = False
    levels = []
    for a, b, q in clipped:
        if a > covered + eps:
            missing = True
        covered = max(covered, b)
        if not any(math.isclose(q, x, rel_tol=0, abs_tol=1e-9) for x in levels):
            levels.append(q)
    if covered < end_min - eps:
        missing = True
    levels = sorted(levels)
    if len(levels) == 1 and not missing:
        return f'{levels[0]:g} W'
    power_text = ', '.join(f'{q:g}' for q in levels) + ' W'
    if missing:
        return 'Q częściowo nieznana; znane: ' + power_text
    return 'Q zmienna: ' + power_text


def stable_positive_power(stages, start_min, end_min):
    """Return (power, reason) iff a contiguous interval has the same Q > 0."""
    eps = 1e-7
    if not (math.isfinite(start_min) and math.isfinite(end_min) and end_min > start_min):
        return None, 'Brak poprawnego okna porównania'
    current = start_min
    power = None
    for stage in sorted(stages, key=lambda s: s.start_min):
        if stage.end_min <= current + eps:
            continue
        if stage.start_min > current + eps:
            return None, 'Q nieznana w części okna odniesienia / epizodu'
        if stage.q_w <= 0:
            return None, 'Okno obejmuje OFF lub zerową Q'
        if power is None:
            power = stage.q_w
        elif not math.isclose(power, stage.q_w, rel_tol=0, abs_tol=1e-9):
            return None, 'Zmiana Q w oknie porównania'
        current = min(end_min, stage.end_min)
        if current >= end_min - eps:
            return power, ''
    return None, 'Q nieznana w części okna odniesienia / epizodu'


def qualify_episode_k2(analysis, episode, resolved_stages, cooling_confirmed=False):
    """Distinguish thermal K2 candidate from power/cooling-qualified comparison.

    The operator confirmation is an experimental assumption, NOT a sensor
    measurement and NOT independent proof of PHP two-phase fluid motion.
    """
    if not episode.oscillatory:
        return K2Review('PRZEJSCIE', 'Przejście termiczne', 'Nie spełnia K1')
    if not episode.k2:
        return K2Review('K1_TYLKO', 'K1, bez K2', 'Brak kryterium termicznego K2')
    t = analysis.record.t
    origin = t[0]
    start_s = max(t[0], episode.start - engine.PRE_BASELINE_START_S)
    end_s = episode.end
    if any(start_s < b and end_s > a for a, b in engine.recording_segments(t)[1]):
        return K2Review('K2_LUKA', 'K2 niezweryfikowane: luka', 'Brak ciągłej rejestracji')
    q, reason = stable_positive_power(resolved_stages,
                                      (start_s-origin)/60, (end_s-origin)/60)
    if q is None:
        return K2Review('K2_Q_NIEPEWNA', 'K2 niezweryfikowane: Q', reason)
    if not cooling_confirmed:
        return K2Review('K2_CHLODZENIE_NIEZNANE', 'K2 termiczne; chłodzenie?',
                        'Q stała, lecz operator nie potwierdził porównywalnych warunków chłodzenia', q)
    return K2Review('K2_WARUNKOWE', 'K2 warunkowo porównywalne',
                    'Q stała; operator zadeklarował porównywalne warunki chłodzenia. '
                    'Nie dowodzi ruchu czynnika ani wzrostu sprawności PHP.', q)


def review_all_k2(analysis, resolved_stages, cooling_confirmed=False):
    return {ep.display_id: qualify_episode_k2(
        analysis, ep, resolved_stages, cooling_confirmed)
            for ep in analysis.episodes if ep.oscillatory}
