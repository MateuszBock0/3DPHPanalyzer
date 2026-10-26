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


def calculate(t_seconds, delta_k, stages: list[PowerStage], ref_range_min: Optional[tuple[float, float]] = None):
    """Return sampled Q, R_app [K/W], R/R_ref, and reference details.

    For normalization a single constant Q>0 must hold in the reference window;
    relative values are restricted to that same power level.
    """
    stages = validate(stages)
    if len(t_seconds) != len(delta_k):
        raise ValueError('Niepasujące długości sygnałów.')
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
        if not math.isfinite(a) or not math.isfinite(b) or a < 0 or a >= b:
            reference_error = 'Błędny przedział odniesienia.'
        else:
            chosen = [(r, power) for t, r, power in zip(t_seconds, rr_abs, q)
                      if a <= (t - origin)/60 <= b and r is not None]
            levels = {power for r, power in chosen}
            if len(chosen) < 5 or len(levels) != 1:
                reference_error = 'R_ref wymaga co najmniej 5 próbek przy jednej dodatniej Q.'
            else:
                reference_q = chosen[0][1]
                reference_r = median(r for r, _ in chosen)
                if not math.isfinite(reference_r) or abs(reference_r) <= 1e-12:
                    reference_error = 'R_ref zerowe lub nieokreślone.'
                    reference_r = reference_q = None
                else:
                    rr = [r / reference_r if r is not None and power is not None
                          and math.isclose(power, reference_q, abs_tol=1e-9, rel_tol=0)
                          else None for r, power in zip(rr_abs, q)]
    return {'q': q, 'r': rr_abs, 'relative': rr, 'r_ref': reference_r,
            'q_ref': reference_q, 'reference_error': reference_error}
