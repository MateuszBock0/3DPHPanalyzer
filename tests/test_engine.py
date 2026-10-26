"""Regression tests for the uploaded temperature-analysis engine, no GUI needed."""
import io
import csv
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

import php_analyzer as engine


def sample(with_gap=False):
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(['', 'Kanał 1 Ostatni (C)', 'Kanał 3 Ostatni (C)',
                 'Kanał 4 Ostatni (C)', 'Kanał 5 Ostatni (C)',
                 'Kanał 6 Ostatni (C)', 'Kanał 7 Ostatni (C)'])
    for i in list(range(130)) + (list(range(200, 330)) if with_gap else []):
        row = [f'{i//3600:02}:{(i//60)%60:02}:{i%60:02}'] + [
            str(70 if ch in (1, 3) else 50 if ch in (4, 5) else 30) + ',25'
            for ch in (1, 3, 4, 5, 6, 7)]
        wr.writerow(row)
    return buf.getvalue().encode('utf-8')


class EngineTests(unittest.TestCase):
    def test_polish_picolog_csv_and_six_channels(self):
        record = engine.parse_csv(sample(), 'a.csv', 'memory')
        self.assertEqual(len(record.t), 130)
        self.assertAlmostEqual(record.values[0][0], 70.25)
        self.assertAlmostEqual(record.values[0][4], 30.25)

    def test_no_interpolation_over_gaps(self):
        record = engine.parse_csv(sample(True), 'a.csv', 'memory')
        sections, gaps = engine.recording_segments(record.t)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0], (129., 200.))
        self.assertEqual(len(sections), 2)

    def test_constant_temperatures_not_false_positive_oscillation(self):
        record = engine.parse_csv(sample(True), 'a.csv', 'memory')
        a = engine.analyze(record)
        self.assertEqual(len(a.delta), 260)
        self.assertAlmostEqual(a.delta[0], 40.0)
        self.assertEqual(sum(x.oscillatory for x in a.episodes), 0)
        self.assertTrue(any('BRAKI DANYCH' in note for note in a.notes))

    def test_nonzero_clock_start_normalized_in_csv_and_png(self):
        header=['', 'Kanał 1 Ostatni (C)','Kanał 3 Ostatni (C)',
                'Kanał 4 Ostatni (C)','Kanał 5 Ostatni (C)',
                'Kanał 6 Ostatni (C)','Kanał 7 Ostatni (C)']
        out=io.StringIO(); w=csv.writer(out);w.writerow(header)
        for i in range(180):
            second=14*3600+i
            w.writerow([f'{second//3600:02}:{(second//60)%60:02}:{second%60:02}']+
                       ['80','80','60','60','40','40'])
        record=engine.parse_csv(out.getvalue().encode(),'afternoon.csv','memory')
        a=engine.analyze(record)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'series.csv'
            engine.export_series(a,path)
            with path.open(encoding='utf-8-sig',newline='') as fh:
                data=list(csv.DictReader(fh,delimiter=';'))
            self.assertAlmostEqual(float(data[0]['czas_od_csv_min']),0)
            self.assertLess(float(data[-1]['czas_od_csv_min']),4)
            from unittest.mock import patch
            captured=[]
            with patch.object(engine.plt,'close',side_effect=lambda fig:
                              captured.append(fig.axes[3].get_xlim())):
                engine.make_plot_png(a,Path(td)/'plot.png')
            self.assertAlmostEqual(captured[0][0],0,places=4)
            self.assertAlmostEqual(captured[0][1],179/60,places=4)
        ep=SimpleNamespace(start=record.t[0]+60,end=record.t[0]+120,
            display_id='O1',oscillatory=True,k2=True,from_heating_on_s=15,
            kind='OSC_AND_DELTA_IMPROVEMENT',peaks=4,troughs=4,
            t_ev=80,t_middle=60,t_co=40,baseline=40,median_delta=30,
            reduction_pct=25,improvement_duration_s=60,rms_max=3,pair_corr=.8)
        a.episodes=[ep]
        self.assertEqual(engine.csv_episodes([a])[0]['poczatek_min_od_csv'],'1.00')
        self.assertEqual(engine.csv_summary([a])[0]['pierwszy_epizod_min_od_csv'],'1.00')

    def test_backward_clock_is_never_silently_sorted(self):
        buf=io.StringIO()
        writer=csv.writer(buf)
        writer.writerow(['',*[f'Kanał {ch} Ostatni (C)' for ch in (1,3,4,5,6,7)]])
        for t in list(range(130))+list(range(100,230)):
            writer.writerow([str(t),80,80,60,60,40,40])
        with self.assertRaisesRegex(ValueError,'Niechronologiczne'):
            engine.parse_csv(buf.getvalue().encode(),'rollback.csv','test')

    def test_bad_csv_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.parse_csv(b'not,a,picolog\n0,1,2\n', 'bad.csv', 'memory')

if __name__ == '__main__':
    unittest.main()
