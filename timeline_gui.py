"""Interactive Matplotlib timeline editing mixin for PHPDesktop.

Do not conflate temperature-inferred timestamps with independently recorded
electrical-switch times. Operator accepts or moves every manual marker.
"""
from __future__ import annotations

from dataclasses import replace
import math
from tkinter import messagebox, simpledialog

from timeline_editor import (Transition, validate_transitions,
                             proposals_from_thermal, snap_to_recorded_sample)
from session_store import save_session


class TimelineInteractionMixin:
    def _duration_min(self):
        record = self._get()['record']
        return (record.t[-1]-record.t[0])/60.

    def _set_chart_mode(self, mode):
        if mode is not None and self.active is None:
            messagebox.showinfo('Zdarzenia', 'Najpierw wczytaj pomiar CSV.')
            return
        self.chart_edit_mode = mode
        labels = {
            'ON':'Kliknij na wykresie chwilę ON. Następnie podaj faktyczną nastawę Q [W].',
            'OFF':'Kliknij na wykresie chwilę OFF; od tego momentu program przyjmie 0 W.',
            'CHANGE_Q':'Kliknij na wykresie zmianę mocy; następnie wpisz nowe Q [W].'
        }
        if isinstance(mode,tuple) and mode[0]=='MOVE':
            text='Kliknij nowe miejsce dla wybranego znacznika ON/OFF/Q.'
        else:
            text=labels.get(mode,'Tryb edycji wyłączony. Możesz przeciągnąć ręczny znacznik na wykresie.')
        self.editor_hint.set(text)
        self.status.set(text)

    def _autosave_current(self):
        if self.active is None:
            return
        try:
            self._get()['session_path'] = str(save_session(self._get()))
        except OSError as exc:
            self.status.set('Uwaga: nie zapisano automatycznej sesji: '+str(exc))

    def _timeline_changed(self, previous):
        row=self._get()
        row.setdefault('undo_events', []).append(list(previous))
        row['undo_events'] = row['undo_events'][-20:]
        self._recalculate(notify=True)
        self._render_power_tree()
        self._render_events()
        self._render_diagnosis()
        self.draw_plot()
        self._autosave_current()
        self.status.set('Zmieniono oś czasu; przeliczono Q, R_app, R/Rref, K2 i ocenę aktywności.')

    def _apply_timeline(self, proposed):
        row=self._get()
        checked=validate_transitions(proposed,self._duration_min()) if proposed else []
        previous=list(row.get('timeline_events', []))
        if checked == previous:
            return
        row['timeline_events']=checked
        self._timeline_changed(previous)

    def _q_for_on(self, kind):
        row=self._get()
        suggested=row.get('constant_q')
        if suggested is None or suggested<=0:
            existing=[e.q_w for e in row.get('timeline_events', [])
                      if e.q_w is not None and e.q_w>0]
            suggested=existing[-1] if existing else 10.
        return simpledialog.askfloat(
            'Rzeczywista nastawa mocy Q',
            'Wpisz ustawioną przez Ciebie moc grzałki dla '+kind+
            ' [W]. To NIE jest moc wyznaczona z temperatur:',
            initialvalue=suggested, minvalue=0.000001, parent=self)

    def _add_marker(self, kind, minute):
        row=self._get()
        if kind=='OFF':
            q=0.
        else:
            q=self._q_for_on(kind)
            if q is None:
                return
        proposed=list(row.get('timeline_events', []))
        proposed.append(Transition(minute,kind,q,'operator'))
        self._apply_timeline(proposed)

    def _on_chart_press(self, event):
        if self.active is None or event.inaxes not in self.axes:
            return
        if event.button != 1 or event.xdata is None or bool(self.toolbar.mode):
            return
        row=self._get()
        mode=self.chart_edit_mode
        try:
            minute=snap_to_recorded_sample(event.xdata,row['record'].t)
            if isinstance(mode,tuple) and mode[0]=='MOVE':
                self._move_transition(mode[1],minute)
                self._set_chart_mode(None)
                return
            if mode in ('ON','OFF','CHANGE_Q'):
                self._add_marker(mode,minute)
                self._set_chart_mode(None)
                return
            near=None
            best=11.
            for i, item in enumerate(row.get('timeline_events', [])):
                x_px=event.inaxes.transData.transform((item.time_min,0))[0]
                dist=abs(event.x-x_px)
                if dist < best:
                    best=dist
                    near=i
            if near is not None:
                self._drag_index=near
                self._drag_lines=self._manual_line_artists.get(near,[])
                self.editor_hint.set('Przesuń pionowy znacznik i puść przycisk myszy.')
        except ValueError as exc:
            messagebox.showwarning('Nie można umieścić znacznika',str(exc),parent=self)

    def _on_chart_motion(self,event):
        if self._drag_index is None or event.xdata is None or event.inaxes not in self.axes:
            return
        for line in self._drag_lines:
            line.set_xdata([event.xdata,event.xdata])
        self.canvas.draw_idle()

    def _on_chart_release(self,event):
        if self._drag_index is None:
            return
        index=self._drag_index
        self._drag_index=None
        self._drag_lines=[]
        if event.inaxes not in self.axes or event.xdata is None:
            self.draw_plot()
            return
        try:
            minute=snap_to_recorded_sample(event.xdata,self._get()['record'].t)
            self._move_transition(index,minute)
        except ValueError as exc:
            self.draw_plot()
            messagebox.showwarning('Nie można przesunąć znacznika',str(exc),parent=self)

    def _move_transition(self,index,minute):
        row=self._get()
        items=list(row.get('timeline_events', []))
        if index<0 or index>=len(items):
            raise ValueError('Wybrany znacznik nie istnieje.')
        items[index]=replace(items[index],time_min=minute)
        self._apply_timeline(items)

    def move_selected_transition(self):
        if self.active is None:
            return
        selection=self.timeline_tree.selection()
        if not selection:
            messagebox.showinfo('Przesuwanie ON/OFF','Wybierz znacznik w tabeli.')
            return
        self.tabs.select(self.chart_page)
        self._set_chart_mode(('MOVE',int(selection[0])))

    def edit_selected_q(self):
        if self.active is None:
            return
        selection=self.timeline_tree.selection()
        if not selection:
            messagebox.showinfo('Moc Q','Wybierz znacznik w tabeli.')
            return
        index=int(selection[0]); row=self._get()
        items=list(row['timeline_events'])
        item=items[index]
        if item.kind=='OFF':
            messagebox.showinfo('OFF','Znacznik OFF zawsze ma Q=0 W. Zmień jego typ przez usunięcie i dodanie ON.')
            return
        result=simpledialog.askfloat('Edytuj Q',f'Nowa moc [{item.kind}] [W]:',
                                     initialvalue=item.q_w,minvalue=0.000001,parent=self)
        if result is None:
            return
        items[index]=replace(item,q_w=result)
        try: self._apply_timeline(items)
        except ValueError as exc: messagebox.showerror('Q',str(exc))

    def delete_transition(self):
        if self.active is None:
            return
        selection=self.timeline_tree.selection()
        if not selection:
            messagebox.showinfo('Znaczniki','Wybierz znacznik z tabeli.')
            return
        index=int(selection[0])
        events=list(self._get().get('timeline_events', []))
        events.pop(index)
        self._apply_timeline(events)

    def undo_timeline(self):
        if self.active is None:
            return
        row=self._get()
        history=row.get('undo_events',[])
        if not history:
            self.status.set('Brak wcześniejszych zmian znaczników do cofnięcia.')
            return
        before=list(row['timeline_events'])
        row['timeline_events']=history.pop()
        self._recalculate()
        self._render_power_tree()
        self._render_events()
        self._render_diagnosis()
        self.draw_plot()
        self._autosave_current()
        self.status.set('Cofnięto zmianę znaczników ON/OFF/Q.')

    def accept_thermal_proposals(self):
        if self.active is None:
            messagebox.showinfo('Sugestie','Najpierw wczytaj CSV.')
            return
        row=self._get()
        count=sum(e.kind in ('HEATING_ON_EST','HEATING_OFF_EST') for e in row['analysis'].heating_events)
        if not count:
            messagebox.showinfo('Sugestie','Brak sugestii ON?/OFF? dla tego pomiaru.')
            return
        if not messagebox.askyesno('Zatwierdź sugestie temperatur',
             f'Program znalazł {count} przybliżonych reakcji ON?/OFF?.\n\n'
             'Czy użyć ich jako EDYTOWALNYCH znaczników?\n'
             'To odpowiedź termiczna, nie elektryczny czas przełączenia!\n'
             'Istniejące ręczne znaczniki zostaną zastąpione. '
             'Ręczne przedziały Q pozostaną bez zmian.',icon='warning',parent=self):
            return
        q=row.get('constant_q')
        if any(e.kind=='HEATING_ON_EST' for e in row['analysis'].heating_events) and (q is None or q<=0):
            q=self._q_for_on('sugestii ON?')
            if q is None:
                return
        try:
            result=proposals_from_thermal(
                row['analysis'].heating_events,row['record'].t[0],
                self._duration_min(),q)
            self._apply_timeline(result)
            self.status.set(f'Zatwierdzono {len(result)} sugestii termicznych. Możesz teraz przesuwać znaczniki.')
        except ValueError as exc:
            messagebox.showerror('Sugestie',str(exc),parent=self)
