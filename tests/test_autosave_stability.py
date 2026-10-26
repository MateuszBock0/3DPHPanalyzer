"""Regression tests for local autosave and quasi-steady thermal reference.

All signals are synthetic; this test file does not publish laboratory measurements.
"""
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from power_model import PowerStage, calculate
from session_config import autosave_path, save_session, restore_session


class AutosaveTests(unittest.TestCase):
    def make_row(self):
        times = list(range(601))
        vals = [(80., 80., 60., 60., 40., 40.) for _ in times]
        record = SimpleNamespace(name="pomiar.csv", origin="folder A",
                                 t=times, values=vals)
        stages = [PowerStage(0., 10., 20.)]
        analysis = SimpleNamespace(te=[80.]*601, tc=[40.]*601,
                                   delta=[40.]*601)
        result = calculate(times, analysis.delta, stages, (2, 5),
                           te=analysis.te, tc=analysis.tc)
        return dict(record=record, analysis=analysis,
                    stages=stages, periods=[], constant_q=None,
                    constant_scope='estimated', effective_stages=stages,
                    ref_enabled=True, ref_start=2., ref_end=5.,
                    results=result)

    def test_roundtrip_without_modifying_input_data(self):
        with tempfile.TemporaryDirectory() as root:
            row = self.make_row()
            path = save_session(row, root)
            self.assertEqual(path, autosave_path(row['record'], root))
            self.assertTrue(path.exists())
            restored = restore_session(row, root)
            self.assertEqual(restored['stages'], row['stages'])
            self.assertTrue(restored['ref_enabled'])
            self.assertAlmostEqual(restored['results']['r_ref'], 2.)

    def test_same_values_moved_to_another_folder_restore(self):
        with tempfile.TemporaryDirectory() as root:
            row = self.make_row()
            save_session(row, root)
            row['record'].origin = "folder B"
            self.assertIsNotNone(restore_session(row, root))

    def test_different_measurement_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as root:
            row = self.make_row()
            save_session(row, root)
            row['record'].values[0] = (81., 80., 60., 60., 40., 40.)
            self.assertIsNone(restore_session(row, root))

    def test_invalid_or_partial_saved_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            row = self.make_row()
            path = autosave_path(row['record'], root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"incomplete":', encoding='utf-8')
            with self.assertRaises(ValueError):
                restore_session(row, root)


class QuasiSteadyReferenceTests(unittest.TestCase):
    def setUp(self):
        self.times = list(range(601))
        self.stages = [PowerStage(0., 10., 20.)]

    def test_stationary_thermal_window_accepted(self):
        te = [80 + .05*math.sin(t/9) for t in self.times]
        tc = [40 + .03*math.sin(t/11) for t in self.times]
        delta = [x-y for x,y in zip(te,tc)]
        out = calculate(self.times, delta, self.stages, (2, 6), te=te, tc=tc)
        self.assertIsNone(out['reference_error'])
        self.assertAlmostEqual(out['r_ref'], 2.0, places=2)

    def test_warmup_drift_is_not_accepted_as_reference(self):
        te = [40 + .04*t for t in self.times]  # 2.4 °C/min warming
        tc = [25.]*len(self.times)
        delta = [x-y for x,y in zip(te,tc)]
        out = calculate(self.times, delta, self.stages, (2, 6), te=te, tc=tc)
        self.assertIsNone(out['r_ref'])
        self.assertIn('quasi-ustalone', out['reference_error'])

    def test_too_short_reference_rejected(self):
        te = [80.]*len(self.times)
        tc = [40.]*len(self.times)
        out = calculate(self.times, [40.]*len(self.times), self.stages,
                        (2, 3), te=te, tc=tc)
        self.assertIn('2 minuty', out['reference_error'])


if __name__ == '__main__':
    unittest.main()
