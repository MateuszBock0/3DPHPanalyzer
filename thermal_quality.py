"""Traceable correction / quality controls for PicoLog six-thermocouple tests.

Coefficients transcribed from the user's 'zestawienie-wykresy(Arkusz1).csv'.
The original PicoLog readings are preserved; this module NEVER infers Q.
Fitted at PT100 setpoints 20..105 degC; use above range is EXTRAPOLATION.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from statistics import median
from copy import copy

CHANNELS=(1,3,4,5,6,7)
COEFFICIENTS={
    1:(0.990584654516796,-0.670008747930264),
    3:(0.986414721484809,-0.488477809059944),
    4:(0.975795742151219,-0.00850596348850955),
    5:(0.978423335606411,0.0885793571218791),
    6:(0.976177788144122,-0.0817258170119446),
    7:(0.980590220739363,-0.224991657827708),
}
FIT_RANGE_C=(20.,105.)
PROFILE_NAME='PT100-zestawienie-wykresy-2026'
PROFILE_SOURCE='zestawienie-wykresy(Arkusz1).csv'


def transform_record(raw, calibrated=False):
    """Return independent record copy, warnings; does not alter raw measurements."""
    result=copy(raw)
    warnings=[]
    if not calibrated:
        return result,warnings
    out=[]
    outside=[0]*len(CHANNELS)
    for row in raw.values:
        converted=[]
        for i,(ch,value) in enumerate(zip(CHANNELS,row)):
            if not isfinite(value):
                raise ValueError(f'TP{ch}: temperatura nie jest skończona.')
            if not FIT_RANGE_C[0]<=value<=FIT_RANGE_C[1]:
                outside[i]+=1
            a,b=COEFFICIENTS[ch]
            converted.append(a*value+b)
        out.append(tuple(converted))
    result.values=out
    for i,count in enumerate(outside):
        if count:
            warnings.append(
                f'TP{CHANNELS[i]}: {count}/{len(out)} próbek poza {FIT_RANGE_C[0]:g}–'
                f'{FIT_RANGE_C[1]:g} °C; korekcja jest EKSTRAPOLACJĄ, bez gwarancji dokładności.')
    warnings.insert(0,f'Zastosowano profil: {PROFILE_NAME}, T_idealna=a*T_surowa+b. '
                    'Oryginalne próbki zachowano osobno.')
    return result,warnings


@dataclass(frozen=True)
class ChannelQuality:
    condenser_median_difference_c: float
    condenser_max_difference_c: float
    middle_tp4_min_c: float
    suspect_tp4: bool
    notes: tuple[str,...]


def assess_quality(record, *, exclude_tp4=False):
    if not record.values:
        raise ValueError('Nie ma próbek do oceny.')
    v=record.values
    d=[abs(q[4]-q[5]) for q in v]
    min4=min(q[2] for q in v)
    # Treat clear sensor failures as warnings, not automatic replacement.
    implausible=sum(q[2] < -20 and q[3] > 0 for q in v)
    suspect=implausible>0
    notes=[]
    if suspect:
        notes.append(f'TP4: {implausible} próbek <-20°C przy TP5 >0°C. '
                     'Możliwa awaria czujnika; sprawdź mocowanie/elektronikę.')
    if median(d)>10:
        notes.append(f'TP6–TP7: mediana |T6-T7| = {median(d):.1f}°C >10°C. '
                     'Nie interpretuj średniej Tc jako temperatury jednorodnej.')
    if exclude_tp4:
        notes.append('TP4 WYŁĄCZONA Z Tm przez operatora. Środkowa temperatura opiera się tylko na TP5.')
    return ChannelQuality(median(d),max(d),min4,suspect,tuple(notes))
