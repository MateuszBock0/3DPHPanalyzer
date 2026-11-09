"""Validated, portable PHP experiment power configuration."""
from __future__ import annotations
import hashlib
import math
import struct
from dataclasses import asdict
from power_model import PowerStage, calculate, validate
from timeline_editor import (Transition, validate_transitions, resolve_schedule,
                             ThermalSuggestion, validate_suggestions, suggested_heating_events)
from power_model import derive_estimated_periods
import php_analyzer as engine
import sensor_profiles

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
        'schema_version': 6, 'filename': r.name, 'source': r.origin,
        'source_identity': record_identity(r),
        'manual_overrides': [asdict(s) for s in row['stages']],
        'calibration_mode': row.get('calibration_mode','raw'),
        'exclude_thermocouple4': bool(row.get('exclude_thermocouple4',False)),
        'calibration_source': ('zestawienie-wykresy(Arkusz1).csv: '
            'T_corr=a*T_raw+b, 20–105 °C fit range'),
        'power_evidence': list(row.get('power_evidence',[])),
        'timeline_events': [asdict(s) for s in row.get('timeline_events', [])],
        **({'thermal_suggestions':[asdict(s) for s in row['thermal_suggestions']]}
           if 'thermal_suggestions' in row else {}),
        'estimated_periods': [asdict(p) for p in row['periods']],
        'constant_q_W': row['constant_q'],
        'constant_q_scope': row['constant_scope'],
        'cooling_conditions_confirmed': bool(row.get('cooling_confirmed', False)),
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
    mode=config.get('calibration_mode','raw')
    if mode not in sensor_profiles.MODES:
        raise ValueError('Nieznany tryb kalibracji termopar.')
    exclude4=config.get('exclude_thermocouple4',False)
    if type(exclude4) is not bool:
        raise ValueError('exclude_thermocouple4 musi być true/false.')
    evidence=config.get('power_evidence',[])
    if not isinstance(evidence,list) or len(evidence)>1000:
        raise ValueError('power_evidence musi być listą.')
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
    cooling_confirmed = config.get('cooling_conditions_confirmed', False)
    if type(cooling_confirmed) is not bool:
        raise ValueError('cooling_conditions_confirmed musi być true/false.')
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
    validated_evidence=[]
    for entry in evidence:
        if not isinstance(entry,dict):
            raise ValueError('Pochodzenie Q musi być obiektem.')
        start_e=_number(entry.get('start_min'),'Q z dziennika od')
        end_e=_number(entry.get('end_min'),'Q z dziennika do')
        voltage=_number(entry.get('voltage_v'),'Napięcie z dziennika')
        current=_number(entry.get('current_a'),'Prąd z dziennika')
        power=sensor_profiles.voltage_current_power(voltage,current)
        if start_e<0 or end_e<=start_e or end_e>duration+1e-7:
            raise ValueError('Etap z dziennika wykracza poza zakres CSV.')
        if not any(abs(st.start_min-start_e)<1e-6 and
                   abs(st.end_min-end_e)<1e-6 and
                   abs(st.q_w-power)<0.001 for st in overrides):
            raise ValueError('Wpis U/I nie ma zgodnego ręcznego przedziału Q.')
        validated_evidence.append(dict(
            start_min=start_e,end_min=end_e,voltage_v=voltage,
            current_a=current,power_w=power,
            source=str(entry.get('source','dziennik U/I'))[:250],
            note=str(entry.get('note',''))[:350]))

    if any(stage.end_min > duration + 1e-8 for stage in overrides):
        raise ValueError('Nadpisanie Q wykracza poza czas pomiaru.')
    raw_events = config.get('timeline_events', [])
    if not isinstance(raw_events, list):
        raise ValueError('timeline_events musi być listą.')
    timeline = []
    for event in raw_events:
        if not isinstance(event, dict):
            raise ValueError('Znacznik ON/OFF/Q musi być obiektem.')
        kind = event.get('kind')
        value = event.get('q_w')
        timeline.append(Transition(
            _number(event.get('time_min'), 'Czas znacznika'), kind,
            _number(value, 'Q znacznika') if value is not None else None,
            event.get('source', 'operator')))
    timeline = validate_transitions(timeline, duration) if timeline else []
    # Legacy v4 configurations did not store editable thermal boundaries.
    raw_suggestions = config.get('thermal_suggestions')
    if raw_suggestions is None:
        suggestions = list(row.get('thermal_suggestions', []))
        periods = row['periods']
    else:
        if not isinstance(raw_suggestions, list) or len(raw_suggestions) > 10000:
            raise ValueError('thermal_suggestions musi być listą o rozsądnym rozmiarze.')
        suggestions = validate_suggestions([
            ThermalSuggestion(_number(x.get('time_min'), 'Czas sugestii'),
                              x.get('kind'), x.get('source', 'automatic'))
            for x in raw_suggestions if isinstance(x, dict)
        ], duration)
        if len(suggestions) != len(raw_suggestions):
            raise ValueError('Każda sugestia musi być obiektem.')
        _seg, gaps = engine.recording_segments(record.t)
        periods = derive_estimated_periods(record.t,
            suggested_heating_events(suggestions, record.t[0]), gaps)
    enabled = config.get('reference_enabled', False)
    if type(enabled) is not bool:
        raise ValueError('reference_enabled musi być true/false.')
    start = _number(config.get('reference_start_min', 0), 'Rref od')
    end = _number(config.get('reference_end_min', 10), 'Rref do')
    if start < 0 or end <= start or (enabled and end > duration + 1e-9):
        raise ValueError('Niepoprawne okno referencji.')
    resolved = resolve_schedule(periods, constant, overrides, duration, scope, timeline)
    analysis=engine.analyze(
        sensor_profiles.process_record(record,mode),
        exclude_thermocouple4=exclude4)
    quality=sensor_profiles.quality_report(record,mode,exclude4)
    analysis.notes.extend(quality.notes())
    result = calculate(record.t, analysis.delta, resolved,
                       (start, end) if enabled else None,
                       te=analysis.te, tc=analysis.tc)
    if result['reference_error']:
        raise ValueError('Nie można przywrócić Rref: ' + result['reference_error'])
    return {'stages': overrides, 'timeline_events': timeline,
            'analysis': analysis,
            'sensor_quality': quality, 'calibration_mode':mode,
            'exclude_thermocouple4':exclude4,
            'power_evidence':validated_evidence,
            'thermal_suggestions': suggestions, 'periods': periods,
            'constant_q': constant, 'constant_scope': scope,
            'cooling_confirmed': cooling_confirmed,
            'ref_enabled': enabled, 'ref_start': start, 'ref_end': end,
            'effective_stages': resolved, 'results': result}
