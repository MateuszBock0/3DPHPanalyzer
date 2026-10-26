"""Validated, portable PHP experiment power configuration."""
from __future__ import annotations
import hashlib
import math
import struct
from dataclasses import asdict
from power_model import PowerStage, calculate, effective_stages, validate

class LegacyConfigurationError(ValueError):
    """Older configuration cannot be verified automatically."""

def record_identity(record):
    digest = hashlib.sha256()
    for time, readings in zip(record.t, record.values):
        digest.update(struct.pack('!d', float(time)))
        for value in readings:
            digest.update(struct.pack('!d', float(value)))
    return {'filename': record.name, 'sample_count': len(record.t),
            'start_s': record.t[0], 'end_s': record.t[-1],
            'values_sha256': digest.hexdigest()}

def export_configuration(row):
    r = row['record']
    result = row['results']
    return {
        'schema_version': 2, 'filename': r.name, 'source': r.origin,
        'source_identity': record_identity(r),
        'manual_overrides': [asdict(s) for s in row['stages']],
        'estimated_periods': [asdict(p) for p in row['periods']],
        'constant_q_W': row['constant_q'],
        'constant_q_scope': row['constant_scope'],
        'resolved_stages': [asdict(s) for s in row['effective_stages']],
        'reference_enabled': row['ref_enabled'],
        'reference_start_min': row['ref_start'],
        'reference_end_min': row['ref_end'],
        'r_ref_K_W': result['r_ref'], 'reference_power_W': result['q_ref'],
        'notes': ('Q is provided by the operator, not inferred from temperatures. '
                  'ON?/OFF? are thermal estimates. P_UP? needs an explicit Q override '
                  'in estimated-power mode. R_app is an apparent resistance.')
    }

def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label}: wymagano liczby.')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: wymagano liczby.') from exc
    if not math.isfinite(result):
        raise ValueError(f'{label}: wartość musi być skończona.')
    return result

def validated_import(config, row, *, legacy_confirmed=False):
    """Return validated settings without changing the active measurement."""
    if not isinstance(config, dict):
        raise ValueError('Konfiguracja JSON musi być obiektem.')
    record = row['record']
    if config.get('filename') != record.name:
        raise ValueError(f'Inny plik: konfiguracja dotyczy {config.get("filename")!r}, a wybrano {record.name!r}.')
    identity = config.get('source_identity')
    if identity is None:
        if not legacy_confirmed:
            raise LegacyConfigurationError(
                'Stary JSON nie zawiera odcisku danych i nie może być zweryfikowany. '
                'Sprawdź ręcznie, czy to ten sam pomiar.')
    elif identity != record_identity(record):
        raise ValueError('Konfiguracja nie pasuje do próbek pomiarowych: różne czasy, temperatury lub liczba próbek.')
    constant = config.get('constant_q_W')
    if constant is not None:
        constant = _number(constant, 'Q stałe')
        if constant < 0:
            raise ValueError('Q nie może być ujemna.')
    scope = config.get('constant_q_scope', 'estimated')
    if scope not in ('estimated', 'full'):
        raise ValueError('Nieznany tryb stałej Q.')
    raw = config.get('manual_overrides', [])
    if not isinstance(raw, list):
        raise ValueError('manual_overrides musi być listą.')
    overrides = []
    for i, stage in enumerate(raw):
        if not isinstance(stage, dict):
            raise ValueError('Etap Q musi być obiektem.')
        overrides.append(PowerStage(
            _number(stage.get('start_min'), f'Od {i+1}'),
            _number(stage.get('end_min'), f'Do {i+1}'),
            _number(stage.get('q_w'), f'Q {i+1}')))
    overrides = validate(overrides)
    duration = (record.t[-1] - record.t[0]) / 60
    if any(stage.end_min > duration + 1e-8 for stage in overrides):
        raise ValueError('Nadpisanie Q wykracza poza czas pomiaru.')
    enabled = config.get('reference_enabled', False)
    if type(enabled) is not bool:
        raise ValueError('reference_enabled musi być true/false.')
    start = _number(config.get('reference_start_min', 0), 'Rref od')
    end = _number(config.get('reference_end_min', 10), 'Rref do')
    if start < 0 or end <= start or (enabled and end > duration + 1e-9):
        raise ValueError('Niepoprawne okno referencji.')
    resolved = effective_stages(row['periods'], constant, overrides, duration, scope)
    result = calculate(record.t, row['analysis'].delta, resolved,
                       (start, end) if enabled else None)
    if result['reference_error']:
        raise ValueError('Nie można przywrócić Rref: ' + result['reference_error'])
    return {'stages': overrides, 'constant_q': constant, 'constant_scope': scope,
            'ref_enabled': enabled, 'ref_start': start, 'ref_end': end,
            'effective_stages': resolved, 'results': result}
