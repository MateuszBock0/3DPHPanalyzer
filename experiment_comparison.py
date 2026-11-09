"""Conservative cross-test visual comparison, never pooling unequal Q.

Only the operator-supplied electrical ON is considered confirmed; ON? is
separate and labelled as inferred. Never treat CSV start as electrical ON.
"""
from __future__ import annotations
from math import isfinite

METRICS=('ΔT [K]','Te [°C]','Tc [°C]','T6 [°C]','T7 [°C]',
         'R_app [K/W]','RMS [°C]')


def series_for(row, metric):
    a=row['analysis']
    values=a.record.values
    return {
        'ΔT [K]':a.delta,
        'Te [°C]':a.te,
        'Tc [°C]':a.tc,
        'T6 [°C]':[x[4] for x in values],
        'T7 [°C]':[x[5] for x in values],
        'R_app [K/W]':row['results']['r'],
        'RMS [°C]':a.activity,
    }[metric]


def anchor_seconds(row, alignment='csv'):
    t0=row['record'].t[0]
    if alignment=='csv':
        return t0,'początek CSV'
    if alignment not in ('on','on_estimate'):
        raise ValueError('Nieznany punkt wyrównania eksperymentów.')
    confirmed=sorted((e.time_min for e in row.get('timeline_events',[])
                      if e.kind=='ON' and e.source=='operator'))
    if confirmed:
        return t0+confirmed[0]*60,'ON (operator)'
    if alignment=='on_estimate':
        estimated=sorted((s.time_min for s in row.get('thermal_suggestions',[])
                          if s.kind=='HEATING_ON_EST'))
        if estimated:
            return t0+estimated[0]*60,'ON? (tylko termiczny szacunek)'
    return None,'brak potwierdzonego ON'


def power_levels(row):
    return tuple(sorted(set(round(float(s.q_w),3) for s in
               row.get('effective_stages',[]) if s.q_w>0)))


def suitability_warnings(rows, alignment='csv'):
    messages=[]
    levels=[power_levels(row) for row in rows]
    if not all(len(level)==1 for level in levels):
        messages.append('Co najmniej jeden eksperyment nie ma jednej znanej dodatniej Q. '
                        'Nie porównuj bezpośrednio oporów przy różnych mocach.')
    elif len(set(level[0] for level in levels))>1:
        messages.append('Różne deklarowane Q: '+', '.join(
            f'{q[0]:g} W' for q in levels)+'. To nie są równoważne warunki zasilania.')
    if not all(row.get('cooling_confirmed',False) for row in rows):
        messages.append('Brak potwierdzenia porównywalnego chłodzenia we wszystkich próbach.')
    modes={row.get('calibration_mode','raw') for row in rows}
    if len(modes)>1:
        messages.append('Mieszane profile termopar raw/corrected — przed wnioskowaniem '
                        'ujednolić tryb kalibracji.')
    if alignment!='csv':
        if any(anchor_seconds(row,alignment)[0] is None for row in rows):
            messages.append('Brak ON dla części prób; serie bez punktu odniesienia pominięte.')
        if alignment=='on_estimate':
            messages.append('Przy braku wpisu operatora użyto ON? z temperatur — '
                            'nie jest to potwierdzony moment włączenia.')
    return messages


def finite_samples(t, y, origin):
    """Series may have unknown values of R; never invent a sample."""
    return [(float(time-origin)/60, float(value)) for time,value in zip(t,y)
            if value is not None and isfinite(value)]
