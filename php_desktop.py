#!/usr/bin/env python3
"""3D PHP Analyzer desktop — Tkinter front end for the supplied PHP algorithm."""
from __future__ import annotations

import csv
import io
import json
import math
import os
import queue
import sys
import threading
import traceback
import zipfile
from dataclasses import asdict
from pathlib import Path
from statistics import median
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

os.environ['PHP_ANALYZER_GUI'] = '1'
import php_analyzer as engine
from power_model import PowerStage, calculate, validate


def app_folder() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_FOLDER = app_folder()
DEFAULT_FOLDER = APP_FOLDER / 'Experiments'
COLOR = {'ev': '#ca513e', 'middle': '#988052', 'co': '#2484b5',
         'delta': '#138975', 'r': '#9354b0', 'q': '#bb753f'}


def path_safe(s):
    return engine.safe_name(Path(s).stem)


def input_files(path: Path):
    """Read explicitly selected files/folder; don't accidentally ingest exports."""
    output = []
    if path.is_dir():
        files = sorted(p for p in path.rglob('*') if p.is_file() and
                       'results' not in [x.lower() for x in p.relative_to(path).parts])
    else:
        files = [path]
    for file in files:
        if file.suffix.lower() == '.csv':
            output.append((file.name, str(file), file.read_bytes()))
        elif file.suffix.lower() == '.zip':
            with zipfile.ZipFile(file) as z:
                for entry in z.infolist():
                    if entry.is_dir() or not entry.filename.lower().endswith('.csv'):
                        continue
                    if '__macosx' in entry.filename.lower() or '/results/' in '/' + entry.filename.lower():
                        continue
                    output.append((Path(entry.filename).name, f'{file.name} / {entry.filename}', z.read(entry)))
    return output


def downsample_indices(t, series, max_buckets=1700):
    """Preserve local minima/maxima for each visible signal in bounded plotting work."""
    n = len(t)
    if n <= max_buckets * 3:
        return list(range(n))
    width = max(1, math.ceil(n / max_buckets))
    chosen = {0, n-1}
    for i in range(0, n, width):
        j = min(n, i+width)
        chosen.add(i)
        chosen.add(j-1)
        for signal in series:
            seq = signal[i:j]
            if not seq:
                continue
            chosen.add(i + min(range(len(seq)), key=seq.__getitem__))
            chosen.add(i + max(range(len(seq)), key=seq.__getitem__))
    return sorted(chosen)


class PHPDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('3D PHP Analyzer  |  Thermal Diagnostics')
        self.geometry('1370x900')
        self.minsize(970, 650)
        self.configure(bg='#eef3f7')
        self._configure_style()
        self.record_rows = []  # {record, analysis, stages, result, reference}
        self.active = None
        self.events = queue.Queue()
        self.busy = False
        self._plot_data = None
        self._build_ui()
        self.after(160, self._poll)

    def _configure_style(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#eef3f7')
        style.configure('Surface.TFrame', background='#ffffff')
        style.configure('Heading.TLabel', background='#eef3f7', foreground='#193951', font=('Segoe UI', 18, 'bold'))
        style.configure('Sub.TLabel', background='#eef3f7', foreground='#61798b', font=('Segoe UI', 10))
        style.configure('Surface.TLabel', background='#ffffff', foreground='#31526a', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=(11, 7))
        style.configure('Accent.TButton', font=('Segoe UI', 10, 'bold'), foreground='#ffffff', background='#166385', padding=(13, 8))
        style.map('Accent.TButton', background=[('active', '#104b66')])
        style.configure('Treeview', rowheight=27, font=('Segoe UI', 9), background='#ffffff', fieldbackground='#ffffff')
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        style.configure('TNotebook', background='#eef3f7', borderwidth=0)
        style.configure('TNotebook.Tab', font=('Segoe UI', 10), padding=(15, 9))

    def _build_ui(self):
        head = ttk.Frame(self)
        head.pack(fill='x', padx=20, pady=(15, 12))
        ttk.Label(head, text='3D PHP Analyzer', style='Heading.TLabel').pack(side='left')
        ttk.Label(head, text='  |  Python Desktop · PicoLog · bez PCM', style='Sub.TLabel').pack(side='left', pady=(6, 0))
        self.status = tk.StringVar(value='Wybierz CSV, ZIP albo folder pomiarów, aby rozpocząć.')
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=20, pady=(0, 10))
        for label, callback, sty in [
            ('+ Otwórz pliki CSV/ZIP', self.add_files, 'Accent.TButton'),
            ('Otwórz folder', self.add_folder, 'TButton'),
            ('Analizuj wszystkie', self.analyze_all, 'TButton'),
            ('Eksport wybranego', self.export_selected, 'TButton'),
            ('Eksport całości', self.export_all, 'TButton')]:
            ttk.Button(bar, text=label, command=callback, style=sty).pack(side='left', padx=(0, 8))
        paned = ttk.Panedwindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True, padx=20, pady=(0, 10))
        sidebar = ttk.Frame(paned, style='Surface.TFrame', width=275)
        main = ttk.Frame(paned)
        paned.add(sidebar, weight=1)
        paned.add(main, weight=5)
        ttk.Label(sidebar, text='POMIARY', style='Surface.TLabel', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=12, pady=(13, 9))
        self.listbox = tk.Listbox(sidebar, borderwidth=0, highlightthickness=0, font=('Segoe UI', 10),
                                  bg='#ffffff', fg='#28495c', selectbackground='#d6eaf2',
                                  selectforeground='#204052', activestyle='none')
        self.listbox.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.listbox.bind('<<ListboxSelect>>', self._select)
        ttk.Label(sidebar, text='Wczytaj kilka plików, aby porównać testy.', style='Surface.TLabel',
                  wraplength=235).pack(anchor='w', padx=12, pady=(0, 15))
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both', expand=True)
        self.chart_page = ttk.Frame(self.tabs)
        self.events_page = ttk.Frame(self.tabs)
        self.power_page = ttk.Frame(self.tabs)
        self.tabs.add(self.chart_page, text='Wykresy')
        self.tabs.add(self.events_page, text='Epizody / ON? OFF?')
        self.tabs.add(self.power_page, text='Moc Q / R')
        self._build_chart_page()
        self._build_events_page()
        self._build_power_page()
        foot = ttk.Frame(self)
        foot.pack(fill='x', padx=20, pady=(0, 12))
        self.progress = ttk.Progressbar(foot, mode='determinate', length=150)
        self.progress.pack(side='right')
        ttk.Label(foot, textvariable=self.status, style='Sub.TLabel').pack(side='left', fill='x', expand=True)

    def _build_chart_page(self):
        top = ttk.Frame(self.chart_page)
        top.pack(fill='x', padx=8, pady=(7, 0))
        self.figure = Figure(figsize=(12, 8), dpi=100, facecolor='#ffffff')
        self.axes = self.figure.subplots(3, 1, sharex=True, gridspec_kw={'height_ratios': [3.2, 1.55, 1.55]})
        self.figure.subplots_adjust(left=.075, right=.985, top=.96, bottom=.085, hspace=.13)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.chart_page)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=8)
        toolbar = NavigationToolbar2Tk(self.canvas, self.chart_page, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill='x', padx=5, pady=3)
        controls = ttk.Frame(self.chart_page)
        controls.pack(fill='x', padx=10, pady=4)
        ttk.Label(controls, text='Trzeci wykres:').pack(side='left')
        self.panel_var = tk.StringVar(value='R pozorny [K/W]')
        ttk.Combobox(controls, textvariable=self.panel_var, state='readonly', width=20,
                     values=['R pozorny [K/W]', 'R względny [-]', 'R proxy ΔT/ΔTref', 'Aktywność RMS [°C]', 'Q [W]']
                     ).pack(side='left', padx=9)
        self.panel_var.trace_add('write', lambda *_: self.draw_plot())
        self.show_individual = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Termopary pojedyncze', variable=self.show_individual,
                        command=self.draw_plot).pack(side='left', padx=10)
        self.show_estimated = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Szacowane ON?/OFF?', variable=self.show_estimated,
                        command=self.draw_plot).pack(side='left', padx=10)
        ttk.Button(controls, text='Zapisz PNG/SVG', command=self.save_chart).pack(side='right')

    def _tree(self, parent, columns):
        holder = ttk.Frame(parent)
        holder.pack(fill='both', expand=True, padx=10, pady=10)
        tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show='headings', selectmode='browse')
        for name, title, width in columns:
            tree.heading(name, text=title)
            tree.column(name, width=width, minwidth=75, anchor='center')
        tree.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(holder, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        return tree

    def _build_events_page(self):
        ttk.Label(self.events_page, text='O1/O2 = kandydaci oscylacji termicznych. ON?/OFF? = reakcje cieplne, nie odczyt stanu grzałki.',
                  style='Sub.TLabel', wraplength=950).pack(anchor='w', padx=14, pady=(10, 0))
        frame = ttk.Frame(self.events_page)
        frame.pack(fill='both', expand=True)
        top = ttk.LabelFrame(frame, text='Epizody', padding=3)
        top.pack(fill='both', expand=True, padx=8, pady=5)
        self.episode_tree = self._tree(top, [('id', 'Epizod', 75), ('kind', 'Typ', 180), ('start', 'Od [min]', 100),
                                              ('end', 'Do [min]', 100), ('delta', 'ΔT [K]', 110),
                                              ('k2', 'Poprawa K2', 100), ('peaks', 'Ekstrema', 80)])
        bottom = ttk.LabelFrame(frame, text='Szacowane zmiany grzania', padding=3)
        bottom.pack(fill='both', expand=True, padx=8, pady=5)
        self.onoff_tree = self._tree(bottom, [('kind', 'Rodzaj', 160), ('time', 'Czas [min]', 100),
                                               ('lo', 'Przedział od', 110), ('hi', 'Przedział do', 110),
                                               ('method', 'Metoda', 240)])
        self.notes = tk.StringVar(value='Wczytaj plik, żeby zobaczyć wyniki detekcji.')
        ttk.Label(frame, textvariable=self.notes, wraplength=950, style='Sub.TLabel').pack(fill='x', padx=16, pady=8)

    def _build_power_page(self):
        body = ttk.Frame(self.power_page)
        body.pack(fill='both', expand=True, padx=12, pady=10)
        ttk.Label(body, text='Ręcznie przypisana moc elektryczna Q(t)', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(body, text='Wartości Q nie są estymowane z termopar. Brak Q ≠ 0 W. R=(Te−Tc)/Q tylko dla Q>0.',
                  style='Sub.TLabel').pack(anchor='w', pady=(0, 9))
        self.power_tree = self._tree(body, [('from', 'Od [min]', 140), ('to', 'Do [min]', 140), ('power', 'Q [W]', 140)])
        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=4)
        ttk.Button(buttons, text='+ Dodaj etap Q', command=self.add_stage).pack(side='left', padx=3)
        ttk.Button(buttons, text='Edytuj etap', command=self.edit_stage).pack(side='left', padx=3)
        ttk.Button(buttons, text='Usuń etap', command=self.delete_stage).pack(side='left', padx=3)
        ttk.Label(body, text='Odniesienie R/Rref: wybierz przedział przy stałym Q [W]', style='Sub.TLabel').pack(anchor='w', pady=(16, 4))
        ref_box = ttk.Frame(body)
        ref_box.pack(fill='x')
        self.reference_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(ref_box, text='Włącz', variable=self.reference_enabled, command=self.update_power).pack(side='left', padx=(0, 15))
        ttk.Label(ref_box, text='Od [min]').pack(side='left')
        self.reference_from = tk.StringVar(value='0')
        ttk.Entry(ref_box, width=12, textvariable=self.reference_from).pack(side='left', padx=6)
        ttk.Label(ref_box, text='Do [min]').pack(side='left')
        self.reference_to = tk.StringVar(value='10')
        ttk.Entry(ref_box, width=12, textvariable=self.reference_to).pack(side='left', padx=6)
        ttk.Button(ref_box, text='Przelicz R/Rref', command=self.update_power).pack(side='left', padx=12)
        self.r_info = tk.StringVar(value='R niedostępny, dopóki nie przypiszesz Q.')
        ttk.Label(body, textvariable=self.r_info, style='Sub.TLabel', wraplength=850).pack(anchor='w', pady=12)

    def _set_busy(self, value):
        self.busy = value
        self.configure(cursor='watch' if value else '')
        self.progress['value'] = 0 if not value else self.progress['value']

    def add_files(self):
        chosen = filedialog.askopenfilenames(title='PicoLog CSV / ZIP', filetypes=[('CSV / ZIP', '*.csv *.zip'), ('Wszystkie pliki', '*.*')])
        if chosen:
            self._start_load([Path(x) for x in chosen])

    def add_folder(self):
        initial = str(DEFAULT_FOLDER if DEFAULT_FOLDER.exists() else Path.home())
        folder = filedialog.askdirectory(title='Folder pomiarów', initialdir=initial)
        if folder:
            self._start_load([Path(folder)])

    def _start_load(self, paths):
        if self.busy:
            messagebox.showinfo('Analiza trwa', 'Zakończ bieżące zadanie przed dodaniem plików.')
            return
        self._set_busy(True)
        self.status.set('Odczytywanie plików i analiza termiczna…')
        threading.Thread(target=self._worker, args=(paths,), daemon=True).start()

    def _worker(self, paths):
        try:
            raw = []
            for path in paths:
                raw.extend(input_files(path))
            if not raw:
                raise ValueError('Nie znaleziono CSV w wybranych plikach ani folderach.')
            records, problems = engine.unique_records(raw)
            if not records:
                raise ValueError('Nie znaleziono poprawnych danych PicoLog.\n' + '\n'.join(problems[:8]))
            results = []
            for index, record in enumerate(records):
                self.events.put(('progress', f'Analiza {index + 1}/{len(records)}: {record.name}', (index / len(records)) * 100))
                try:
                    a = engine.analyze(record)
                    results.append({'record': record, 'analysis': a, 'stages': [], 'results': None,
                                    'ref_enabled': False, 'ref_start': 0., 'ref_end': 10.})
                except Exception as error:
                    problems.append(f'{record.name}: {error}')
            self.events.put(('loaded', results, problems))
        except Exception:
            self.events.put(('error', traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                kind, *rest = self.events.get_nowait()
                if kind == 'progress':
                    self.status.set(rest[0]); self.progress['value'] = rest[1]
                elif kind == 'loaded':
                    results, errors = rest
                    prior = {entry['record'].origin for entry in self.record_rows}
                    added = 0
                    for r in results:
                        if r['record'].origin in prior:
                            continue
                        self.record_rows.append(r)
                        self.listbox.insert('end', r['record'].name)
                        added += 1
                    self._set_busy(False)
                    if self.record_rows:
                        self.listbox.select_clear(0, 'end')
                        self.listbox.select_set(len(self.record_rows) - 1)
                        self._select()
                    self.status.set(f'Wczytano {added} pomiarów. ' + (f'Ostrzeżenia: {len(errors)}.' if errors else ''))
                    if errors:
                        messagebox.showwarning('Pominięte dane / ostrzeżenia', '\n'.join(errors[:12]))
                elif kind == 'error':
                    self._set_busy(False); self.status.set('Błąd analizy')
                    messagebox.showerror('Błąd', rest[0][:5000])
        except queue.Empty:
            pass
        self.after(160, self._poll)

    def _select(self, *_):
        idx = self.listbox.curselection()
        if not idx:
            return
        self.active = int(idx[0])
        row = self.record_rows[self.active]
        self.reference_enabled.set(row['ref_enabled'])
        self.reference_from.set(str(row['ref_start']))
        self.reference_to.set(str(row['ref_end']))
        self._render_power_tree()
        self._recalculate(notify=False)
        self._render_events()
        self.draw_plot()

    def _get(self):
        if self.active is None:
            raise ValueError('Najpierw wczytaj i wybierz pomiar.')
        return self.record_rows[self.active]

    def _render_power_tree(self):
        self.power_tree.delete(*self.power_tree.get_children())
        for i, st in enumerate(self._get()['stages']):
            self.power_tree.insert('', 'end', iid=str(i), values=(f'{st.start_min:.3f}', f'{st.end_min:.3f}', f'{st.q_w:.3f}'))

    def _stage_dialog(self, initial=None):
        data = initial or PowerStage(0., (self._get()['record'].t[-1] - self._get()['record'].t[0])/60., 10.)
        dialog = tk.Toplevel(self)
        dialog.title('Etap mocy Q')
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        vars_ = [tk.StringVar(value=str(v)) for v in (data.start_min, data.end_min, data.q_w)]
        for i, lab in enumerate(('Od [min]', 'Do [min]', 'Q [W]')):
            ttk.Label(dialog, text=lab).grid(row=i, column=0, padx=15, pady=9, sticky='w')
            ttk.Entry(dialog, textvariable=vars_[i], width=24).grid(row=i, column=1, padx=15, pady=9)
        answer = []
        def accept():
            try:
                values = [float(v.get().replace(',', '.')) for v in vars_]
                st = PowerStage(*values)
                validate([st])
                answer.append(st); dialog.destroy()
            except Exception as error:
                messagebox.showerror('Błędny etap', str(error), parent=dialog)
        ttk.Button(dialog, text='Zapisz', command=accept, style='Accent.TButton').grid(row=3, column=0, columnspan=2, pady=13)
        self.wait_window(dialog)
        return answer[0] if answer else None

    def add_stage(self):
        if self.active is None:
            return
        stages = self._get()['stages']
        previous = stages[-1] if stages else None
        duration = (self._get()['record'].t[-1] - self._get()['record'].t[0]) / 60
        proposal = PowerStage(previous.end_min, duration, previous.q_w) if previous and previous.end_min < duration else None
        st = self._stage_dialog(proposal)
        if st:
            try: validate(stages+[st])
            except ValueError as e: return messagebox.showerror('Moc Q', str(e))
            stages.append(st); self._render_power_tree(); self.update_power()

    def edit_stage(self):
        if self.active is None:
            return
        sel = self.power_tree.selection()
        if not sel:
            return messagebox.showinfo('Etap Q', 'Najpierw wybierz wiersz.')
        i = int(sel[0]); stages = self._get()['stages']
        st = self._stage_dialog(stages[i])
        if st:
            copy = stages.copy(); copy[i] = st
            try: validate(copy)
            except ValueError as e: return messagebox.showerror('Moc Q', str(e))
            stages[i] = st; self._render_power_tree(); self.update_power()

    def delete_stage(self):
        if self.active is None:
            return
        sel = self.power_tree.selection()
        if sel:
            self._get()['stages'].pop(int(sel[0])); self._render_power_tree(); self.update_power()

    def update_power(self):
        if self.active is None:
            return
        row = self._get()
        try:
            start = float(self.reference_from.get().replace(',', '.'))
            end = float(self.reference_to.get().replace(',', '.'))
            row['ref_enabled'] = self.reference_enabled.get()
            row['ref_start'], row['ref_end'] = start, end
            self._recalculate(notify=True)
            self.draw_plot()
        except ValueError as e:
            messagebox.showerror('Okno referencyjne', str(e))

    def _recalculate(self, notify=False):
        row = self._get()
        a = row['analysis']
        ref = ((row['ref_start'], row['ref_end']) if row['ref_enabled'] else None)
        row['results'] = calculate(a.record.t, a.delta, row['stages'], ref)
        r = row['results']
        if r['reference_error']:
            self.r_info.set(r['reference_error'] + ' Wartości R/Rref pozostają puste.')
            if notify: self.status.set('Uwaga: ' + r['reference_error'])
        elif r['r_ref'] is not None:
            self.r_info.set(f'Rref = {r["r_ref"]:.5g} K/W dla Q = {r["q_ref"]:g} W; względny R liczony wyłącznie przy tej samej Q.')
        elif row['stages']:
            self.r_info.set('R_app = ΔT/Q dla zdefiniowanych okresów Q > 0; poza nimi brak wartości R. Zmiany Q nie są przełączeniami wywnioskowanymi z temperatur.')
        else:
            self.r_info.set('Q nieznane — R [K/W] nie jest obliczane; wykres R proxy można oglądać osobno.')

    def _render_events(self):
        row = self._get(); a = row['analysis']; rec = row['record']
        self.episode_tree.delete(*self.episode_tree.get_children())
        self.onoff_tree.delete(*self.onoff_tree.get_children())
        first = rec.t[0]
        for ep in a.episodes:
            if not ep.oscillatory:
                continue
            self.episode_tree.insert('', 'end', values=(ep.display_id, ep.kind,
                f'{(ep.start-first)/60:.2f}', f'{(ep.end-first)/60:.2f}',
                f'{ep.median_delta:.2f}', 'tak' if ep.k2 else 'nie', ep.peaks))
        for event in a.heating_events:
            self.onoff_tree.insert('', 'end', values=(event.kind.replace('HEATING_', '').replace('_EST', '?'),
                f'{(event.time-first)/60:.2f}',
                f'{(event.band_start-first)/60:.2f}' if event.band_start is not None else '—',
                f'{(event.band_end-first)/60:.2f}' if event.band_end is not None else '—',
                event.method))
        self.notes.set('; '.join(a.notes) if a.notes else 'Brak ostrzeżeń. Metody detekcji stanowią kryteria robocze, nie pomiar przepływu.')

    def draw_plot(self):
        for ax in self.axes: ax.clear()
        if self.active is None:
            self.axes[0].text(.5, .5, 'Wczytaj plik CSV lub ZIP, aby zobaczyć przebieg.',
                              ha='center', va='center', transform=self.axes[0].transAxes, color='#698294')
            self.canvas.draw_idle(); return
        row = self._get(); a = row['analysis']; rec = row['record']; res = row['results']
        t0 = rec.t[0]
        ts = [(v-t0)/60 for v in rec.t]
        series = [a.te, a.tm, a.tc, a.delta, a.delta_smooth]
        ax, middle, bottom = self.axes
        modes = {'R pozorny [K/W]': ('r', COLOR['r'], 'R_app [K/W]'),
                 'R względny [-]': ('relative', COLOR['r'], 'R/Rref [−]'),
                 'R proxy ΔT/ΔTref': ('proxy', COLOR['r'], 'ΔT/ΔTref [−] (proxy)'),
                 'Aktywność RMS [°C]': ('rms', '#af6639', 'RMS [°C]'),
                 'Q [W]': ('q', COLOR['q'], 'Q [W]')}
        field, color, title = modes.get(self.panel_var.get(), modes['R pozorny [K/W]'])
        values = {'r': res['r'], 'relative': res['relative'], 'proxy': a.r_rel_proxy,
                  'rms': a.activity, 'q': res['q']}[field]
        # Draw segments separately: never draw a synthetic connecting line over missing log data.
        segments, gaps = engine.recording_segments(rec.t)
        for part, (begin, end) in enumerate(segments):
            idx0 = downsample_indices(ts[begin:end], [signal[begin:end] for signal in series])
            idx = [begin + i for i in idx0]
            X = [ts[i] for i in idx]
            if self.show_individual.get():
                for pos, c in [(0, COLOR['ev']), (1, COLOR['ev']), (2, COLOR['middle']),
                               (3, COLOR['middle']), (4, COLOR['co']), (5, COLOR['co'])]:
                    ax.plot(X, [rec.values[i][pos] for i in idx], color=c, linewidth=.7, alpha=.3)
            for signal, c, name in [(a.te, COLOR['ev'], 'Parownik ch1, ch3'),
                                    (a.tm, COLOR['middle'], 'Sekcja środkowa ch4, ch5'),
                                    (a.tc, COLOR['co'], 'Skraplacz ch6, ch7')]:
                ax.plot(X, [signal[i] for i in idx], color=c, linewidth=1.8,
                        label=name if part == 0 else '_nolegend_')
            middle.plot(X, [a.delta[i] for i in idx], color='#9cb4c6', linewidth=.9,
                        alpha=.7, label='ΔT chwilowe' if part == 0 else '_nolegend_')
            middle.plot(X, [a.delta_smooth[i] for i in idx], color=COLOR['delta'], linewidth=2,
                        label='ΔT wygładzone' if part == 0 else '_nolegend_')
            yy = [values[i] if values[i] is not None and math.isfinite(values[i])
                  else float('nan') for i in idx]
            bottom.plot(X, yy, color=color, linewidth=1.8, label=title if part == 0 else '_nolegend_',
                        drawstyle='steps-post' if field=='q' else 'default')
        if field == 'relative': bottom.axhline(1, ls='--', color='#7f9aaa', lw=1)
        if field == 'rms': bottom.axhline(a.threshold, ls='--', color='#ad693d', lw=1, label='Próg K1')
        for span in a.episodes:
            if span.oscillatory:
                c = '#c4e4dc' if span.k2 else '#f8ead2'
                for axis in self.axes: axis.axvspan((span.start-t0)/60, (span.end-t0)/60, color=c, alpha=.33)
        segments, gaps = engine.recording_segments(rec.t)
        for left, right in gaps:
            for axis in self.axes: axis.axvspan((left-t0)/60, (right-t0)/60, color='#aebec8', alpha=.35, zorder=0)
        if self.show_estimated.get():
            for h in a.heating_events:
                c = '#577697' if h.kind.endswith('ON_EST') else '#8d74a7'
                for axis in self.axes: axis.axvline((h.time-t0)/60, color=c, ls=':', lw=1.1, alpha=.8)
                ax.text((h.time-t0)/60, .95, 'ON?' if h.kind.endswith('ON_EST') else
                        'OFF?' if h.kind.endswith('OFF_EST') else 'P↑?',
                        rotation=90, color=c, fontsize=8, va='top', ha='left', transform=ax.get_xaxis_transform())
        for stage in row['stages']:
            for axis in self.axes: axis.axvline(stage.start_min, color=COLOR['q'], ls='--', lw=.65, alpha=.5)
        ax.set_ylabel('Temperatura [°C]')
        middle.set_ylabel('ΔT [K]')
        bottom.set_ylabel(title)
        bottom.set_xlabel('Czas od początku rejestracji [min]')
        for axis in self.axes:
            axis.grid(alpha=.22)
            axis.set_xlim(ts[0], ts[-1])
            axis.spines[['top', 'right']].set_visible(False)
            axis.tick_params(labelsize=9)
        ax.legend(loc='upper left', fontsize=8, frameon=False, ncol=3)
        middle.legend(loc='upper left', fontsize=8, frameon=False)
        if field=='rms': bottom.legend(loc='upper left', fontsize=8, frameon=False)
        self.figure.suptitle(rec.name + ' | 3D PHP (bez PCM)', fontweight='semibold', fontsize=13, y=.997)
        self.canvas.draw_idle()

    def save_chart(self):
        if self.active is None: return
        file = filedialog.asksaveasfilename(title='Eksport wykresu', defaultextension='.png',
                 initialfile=path_safe(self._get()['record'].name) + '_wykres.png',
                 filetypes=[('PNG', '*.png'), ('SVG', '*.svg'), ('PDF', '*.pdf')])
        if file:
            try:
                self.figure.savefig(file, dpi=180, facecolor='white', bbox_inches='tight')
                self.status.set('Zapisano: ' + file)
            except Exception as e: messagebox.showerror('Eksport', str(e))

    def analyze_all(self):
        if not self.record_rows:
            return self.add_folder()
        self.status.set(f'Przeanalizowano {len(self.record_rows)} pomiarów; wybierz Eksport całości, aby zapisać raporty.')
        self.tabs.select(self.events_page)

    @staticmethod
    def _writer(file, headers, rows):
        with open(file, 'w', encoding='utf-8-sig', newline='') as target:
            w = csv.writer(target, delimiter=';')
            w.writerow(headers)
            w.writerows(rows)

    def _export_power(self, row, out):
        a = row['analysis']; t0 = a.record.t[0]; r = row['results']
        headers = ['czas_min', 'Te_C', 'Tm_C', 'Tc_C', 'DeltaT_K', 'Q_W', 'R_app_K_W', 'R_Rref']
        rows = [[f'{(t-t0)/60:.5f}', f'{te:.4f}', f'{tm:.4f}', f'{tc:.4f}', f'{dt:.4f}',
                 '' if q is None else f'{q:.4f}', '' if x is None else f'{x:.7f}',
                 '' if y is None else f'{y:.7f}']
                for t,te,tm,tc,dt,q,x,y in zip(a.record.t, a.te, a.tm, a.tc, a.delta,
                                                r['q'],r['r'],r['relative'])]
        self._writer(out/'moc_i_opor.csv', headers, rows)
        self._writer(out/'przedzialy_Q.csv', ['od_min', 'do_min', 'Q_W'],
                     [[s.start_min, s.end_min, s.q_w] for s in row['stages']])
        config = {'filename': a.record.name, 'source': a.record.origin,
                  'stages': [asdict(s) for s in row['stages']],
                  'reference_enabled': row['ref_enabled'],
                  'reference_start_min': row['ref_start'], 'reference_end_min': row['ref_end'],
                  'r_ref_K_W': r['r_ref'], 'reference_power_W': r['q_ref'],
                  'notes': 'Q is manually specified, never estimated from temperature. R_app is apparent.'}
        (out/'konfiguracja.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')

    def _export_one(self, row, folder):
        a = row['analysis']
        folder.mkdir(parents=True, exist_ok=True)
        plotdir = folder/'wykresy'; plotdir.mkdir(exist_ok=True)
        engine.write_png(a, plotdir)
        engine.make_heating_diagnostics(a, plotdir)
        engine.export_series(a, folder/'przebieg_analityczny.csv')
        self._export_power(row, folder)

    def export_selected(self):
        if self.active is None: return messagebox.showinfo('Eksport', 'Najpierw wybierz pomiar.')
        where = filedialog.askdirectory(title='Katalog wyników', initialdir=str(Path.home()))
        if not where: return
        try:
            row=self._get(); path = Path(where)/path_safe(row['record'].name)
            self._export_one(row, path)
            self.figure.savefig(path/'aktualny_wykres.png', dpi=180, bbox_inches='tight', facecolor='white')
            messagebox.showinfo('Eksport', 'Gotowe. Wyniki zapisano:\n' + str(path))
        except Exception: messagebox.showerror('Eksport', traceback.format_exc())

    def export_all(self):
        if not self.record_rows: return messagebox.showinfo('Eksport', 'Najpierw wczytaj dane.')
        where = filedialog.askdirectory(title='Katalog pełnego raportu', initialdir=str(Path.home()))
        if not where: return
        out = Path(where)/'PHP_Results'; out.mkdir(parents=True, exist_ok=True)
        try:
            analyses, idx = [], {}
            for row in self.record_rows:
                r = row['analysis']
                folder = out/path_safe(r.record.name)
                self._export_one(row, folder)
                analyses.append(r)
                idx[r.record.name] = (path_safe(r.record.name)+'/wykresy/'+
                    engine.safe_name(Path(r.record.name).stem)+'_analiza.png', [], None)
            summary = engine.csv_summary(analyses)
            events = engine.csv_episodes(analyses)
            with (out/'Raport.html').open('w', encoding='utf-8') as f:
                f.write(engine.render_html(analyses, summary, events, idx, [], []))
            self._writer(out/'podsumowanie_testow.csv', list(summary[0]) if summary else [],
                         [[x.get(k, '') for k in summary[0]] for x in summary] if summary else [])
            messagebox.showinfo('Eksport', f'Zapisano {len(analyses)} pomiarów w:\n{out}')
        except Exception: messagebox.showerror('Eksport', traceback.format_exc())


def main():
    try:
        program = PHPDesktop()
    except tk.TclError:
        raise SystemExit('Wymagany jest graficzny pulpit Windows/Linux/macOS z Tkinter.')
    program.mainloop()


if __name__ == '__main__':
    main()
