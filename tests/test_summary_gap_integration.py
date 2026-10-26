"""Integrated PicoLog blank-row / gap validation without publishing lab data."""
import csv
import io
import unittest

import php_analyzer as engine
from experiment_summary import build_experiment_summary
from power_model import calculate


class SummaryRealisticGapTests(unittest.TestCase):
    def test_58_minute_blank_section_remains_a_gap_not_false_activity(self):
        out=io.StringIO()
        writer=csv.writer(out)
        writer.writerow(['',*[f'Kanał {ch} Ostatni (C)' for ch in (1,3,4,5,6,7)]])
        # Original laboratory archive contains long blank rows; this is
        # synthetic data with the same missing-data structure, not the
        # user's confidential measurements.
        for second in range(4000):
            stamp=f'{second//3600:02}:{(second//60)%60:02}:{second%60:02}'
            if 180<=second<3650:
                writer.writerow([stamp]+['']*6)
            else:
                writer.writerow([stamp]+['80','80','60','60','40','40'])
        record=engine.parse_csv(out.getvalue().encode('utf-8'), 'gap.csv','synthetic')
        self.assertEqual(record.bad_rows,3470)
        segments,gaps=engine.recording_segments(record.t)
        self.assertEqual(len(gaps),1)
        self.assertEqual(gaps[0],(179.,3650.))
        analysis=engine.analyze(record)
        self.assertFalse(any(ep.oscillatory for ep in analysis.episodes))
        self.assertTrue(any('BRAKI DANYCH' in note for note in analysis.notes))
        row={'record':record,'analysis':analysis,'effective_stages':[],
             'results':calculate(record.t,analysis.delta,[]),
             'stages':[],'timeline_events':[],
             'thermal_suggestions':[]}
        overview=build_experiment_summary(row)
        self.assertEqual(overview.count,0)
        self.assertEqual(overview.q_display,'Q nieznana')
        self.assertIsNone(overview.first_from_on_min)
        self.assertEqual(overview.r_display,'—')


if __name__=='__main__':
    unittest.main()
