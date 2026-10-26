"""Regression tests for the uploaded temperature-analysis engine, no GUI needed."""
import io
import csv
import unittest

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

    def test_bad_csv_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.parse_csv(b'not,a,picolog\n0,1,2\n', 'bad.csv', 'memory')

if __name__ == '__main__':
    unittest.main()
