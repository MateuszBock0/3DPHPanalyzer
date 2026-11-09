"""Non-destructive thermocouple calibration and quality overlay.

The 3D PHP source CSV is immutable. Corrected readings are a separate copy;
the 20–105 °C fit is not validated outside that interval. Calibration
coefficients are transcribed from zestawienie-wykresy(Arkusz1).csv supplied
with the 3–6 November 2026 laboratory records.
"""
from __future__ import annotations
from dataclasses import dataclass
from copy import copy
from math import isfinite

CHANNELS=(1,3,4,5,6,7)
COEFFS={
    1:(0.990584654516796,-0.670008747930264),
    3:(0.986414721484809,-0.488477809059944),
    4:(0.975795742151219,-0.00850596348850955),
    5:(0.978423335606411,0.0885793571218791),
    6:(0.976177788144122,-0.0817258170119446),
    7:(0.980590220739363,-0.224991657827708),
}
VALID_MIN_C=20.
VALID_MAX_C=105.
MODES=('raw','corrected')


@dataclass(frozen=True)
class SensorQuality:
    extrapolated: tuple[tuple[int,int],...]
    ch4_outliers: int
    condenser_disagreement: int
    total_samples: int
    ch4_excluded: bool
    calibration_mode: str

    def notes(self):
        notes=[]
        if self.calibration_mode=='corrected':
            notes.append('Korekcja liniowa z zestawienie-wykresy; zakres dopasowania '
                         '20–105°C. Dane surowe pozostają nienaruszone.')
            counts=dict(self.extrapolated)
            active=[f'T{ch}: {n}' for ch,n in counts.items() if n]
            if active:
                notes.append('EKSTRAPOLACJA poza 20–105°C w próbkach: '+', '.join(active)
                             +'. Dokładność poza zakresem nie została zwalidowana.')
        if self.ch4_outliers:
            notes.append(f'T4: {self.ch4_outliers} próbek surowych poniżej -20°C '
                         'lub powyżej 250°C — podejrzenie błędu czujnika; '
                         'sprawdź również kontakt i skoki sygnału.')
        if self.ch4_excluded:
            notes.append('T4 wykluczono Z INTERPRETACJI środkowej: pokazywane Tm=T5 '
                         '(jeden punkt), nie średnia T4/T5. Surowy T4 zachowany.')
        if self.condenser_disagreement:
            notes.append(f'T6/T7: |T6−T7| > 20 K w {self.condenser_disagreement} '
                         f'z {self.total_samples} próbek; Tc jest średnią dwóch '
                         'punktów o znacznym rozrzucie przestrzennym.')
        return notes


def process_record(raw_record, mode='raw'):
    """Copy temperatures for analysis, preserving raw input for identity/autosave."""
    if mode not in MODES:
        raise ValueError('Nieznany tryb kalibracji termopar.')
    record=copy(raw_record)
    if mode=='raw':
        return record
    record.values=[
        tuple(COEFFS[ch][0]*values[i]+COEFFS[ch][1]
              for i,ch in enumerate(CHANNELS))
        for values in raw_record.values
    ]
    return record


def quality_report(raw_record, mode='raw', exclude_t4=False):
    if mode not in MODES:
        raise ValueError('Nieznany tryb kalibracji.')
    extrapolated=tuple((ch,sum(not VALID_MIN_C<=r[i]<=VALID_MAX_C
                               for r in raw_record.values))
                       for i,ch in enumerate(CHANNELS))
    ch4_errors=sum(v[2]<-20 or v[2]>250 for v in raw_record.values)
    condenser=sum(abs(v[4]-v[5])>20 for v in raw_record.values)
    return SensorQuality(extrapolated,ch4_errors,condenser,
                         len(raw_record.t),bool(exclude_t4),mode)


def voltage_current_power(voltage, current):
    """A point measurement from operator notes, not a PicoLog power channel."""
    u=float(voltage)
    i=float(current)
    if not (isfinite(u) and isfinite(i) and u>0 and i>0):
        raise ValueError('U [V] i I [A] muszą być skończone i dodatnie.')
    return u*i
