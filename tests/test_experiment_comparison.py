"""Regression checks for scientific caveats in cross-experiment overlays."""
import unittest
from types import SimpleNamespace

import experiment_comparison as cmp
from power_model import PowerStage
from timeline_editor import Transition, ThermalSuggestion


class ComparisonTests(unittest.TestCase):
    def row(self,q=10,cal='raw',cool=True):
        r=SimpleNamespace(name='test.csv',t=list(range(181)),
                          values=[(100,100,80,80,70,90)]*181)
        a=SimpleNamespace(record=r,te=[100]*181,tm=[80]*181,
                          tc=[80]*181,delta=[20]*181,activity=[1]*181)
        return {'record':r,'analysis':a,'results':{'r':[2]*181},
                'timeline_events':[],
                'thermal_suggestions':[],
                'effective_stages':[PowerStage(0,3,q)],
                'calibration_mode':cal,'cooling_confirmed':cool}

    def test_series_separate_condenser_thermocouples(self):
        row=self.row()
        self.assertEqual(cmp.series_for(row,'T6 [°C]')[0],70)
        self.assertEqual(cmp.series_for(row,'T7 [°C]')[0],90)
        self.assertEqual(cmp.series_for(row,'ΔT [K]')[0],20)

    def test_manual_on_alignment_is_not_guessed_from_file_start(self):
        row=self.row()
        self.assertEqual(cmp.anchor_seconds(row,'on')[0],None)
        row['thermal_suggestions']=[ThermalSuggestion(1,'HEATING_ON_EST')]
        self.assertEqual(cmp.anchor_seconds(row,'on')[0],None)
        self.assertEqual(cmp.anchor_seconds(row,'on_estimate')[0],60)
        row['timeline_events']=[Transition(0.5,'ON',10,'operator')]
        self.assertEqual(cmp.anchor_seconds(row,'on')[0],30)
        self.assertEqual(cmp.anchor_seconds(row,'on_estimate')[0],30)

    def test_power_and_cooling_mismatch_not_hidden(self):
        a=self.row(10)
        b=self.row(20,cool=False,cal='corrected')
        warnings=cmp.suitability_warnings([a,b])
        self.assertTrue(any('Różne' in w for w in warnings))
        self.assertTrue(any('chłodzenia' in w for w in warnings))
        self.assertTrue(any('Mieszane' in w for w in warnings))

    def test_ambiguous_power_levels_warned(self):
        a=self.row()
        b=self.row()
        b['effective_stages']=[PowerStage(0,1,10),PowerStage(1,3,15)]
        self.assertTrue(any('nie ma jednej' in w
                            for w in cmp.suitability_warnings([a,b]))


if __name__=='__main__':
    unittest.main()
