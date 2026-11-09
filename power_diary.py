"""Extract U/I readings from supplied 'drut' diary CSV; no time synchronisation.

This is an audit helper only. The operator must choose one entry and put
Q=U*I into a confirmed ON/Q marker; clock time alone does not certify ON.
"""
from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DiaryPowerPoint:
    line: int
    time_label: str
    voltage_v: float
    current_a: float
    power_w: float
    source: str


def numeric(text):
    if not text or not str(text).strip():
        return None
    try:
        n=float(str(text).strip().replace(' ','').replace(',','.'))
    except ValueError:
        return None
    return n if isfinite(n) else None


def read_diary(data: bytes, name='drut.csv'):
    # The original sheet export contains CP1250 Polish strings and semicolons.
    decoded=None
    for encoding in ('utf-8-sig','cp1250'):
        try:
            decoded=data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError('Dziennik: nieobsługiwane kodowanie.')
    rows=list(csv.reader(io.StringIO(decoded),delimiter=';'))
    # Accept only the fixed published drut sheet structure, never arbitrary
    # adjacent values and never the wire's calculated nominal resistance Q.
    header=next((i for i,row in enumerate(rows)
                 if len(row)>10 and 'godzina ustawienia' in row[4].lower()
                 and ('napi' in row[7].lower()) and ('nat' in row[8].lower())),None)
    if header is None:
        raise ValueError('Brak nagłówków dziennika: godzina ustawienia, U [V], I [A].')
    values=[]
    for i,row in enumerate(rows[header+1:],header+2):
        if len(row)<11:
            continue
        u=numeric(row[7])
        current=numeric(row[8])
        if u is None or current is None or not (0<u<=100 and 0<current<=20):
            continue
        clock=row[4].strip()
        # In the sheet time is sometimes absent or not reliably synchronised.
        if clock and not (clock.count(':') in (1,2) and
                          all(part.isdigit() for part in clock.split(':'))):
            clock=''
        values.append(DiaryPowerPoint(i,clock,u,current,u*current,name))
    if not values:
        raise ValueError('Nie znaleziono par U i I w dzienniku.')
    return values
