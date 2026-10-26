"""Tests for provisional thermal ON?/OFF? intervals and Q precedence."""
import unittest
from types import SimpleNamespace
from power_model import (PowerStage, derive_estimated_periods,
                         effective_stages, calculate)


def event(time, kind):
    return SimpleNamespace(time=time, kind=kind)


class EstimatedPowerTests(unittest.TestCase):
    def setUp(self):
        self.times = list(range(0, 901))
        self.events = [event(120, 'HEATING_ON_EST'),
                       event(480, 'HEATING_OFF_EST'),
                       event(720, 'HEATING_ON_EST')]
        self.periods = derive_estimated_periods(self.times, self.events)

    def test_periods_are_provisional_and_include_unknown(self):
        self.assertEqual([p.state for p in self.periods],
                         ['UNKNOWN', 'ON?', 'OFF?', 'ON?'])
        self.assertEqual([(p.start_min, p.end_min) for p in self.periods],
                         [(0, 2), (2, 8), (8, 12), (12, 15)])

    def test_detection_alone_does_not_invent_power(self):
        self.assertEqual(effective_stages(self.periods, None, [], 15), [])
        self.assertTrue(all(v is None for v in calculate(self.times, [20.]*901, [])['q']))

    def test_constant_power_applies_to_inferred_on_off_only(self):
        stages = effective_stages(self.periods, 20, [], 15)
        self.assertEqual(stages, [PowerStage(2, 8, 20),
                                  PowerStage(8, 12, 0),
                                  PowerStage(12, 15, 20)])
        result = calculate([0, 180, 600, 780], [40.]*4, stages)
        self.assertEqual(result['q'], [None, 20, 0, 20])
        self.assertEqual(result['r'], [None, 2, None, 2])

    def test_manual_override_splits_on_interval(self):
        overrides = [PowerStage(4, 5, 12), PowerStage(10, 11, 5)]
        stages = effective_stages(self.periods, 20, overrides, 15)
        result = calculate([0, 180, 250, 280, 310, 550, 610, 650, 780],
                           [40.]*9, stages)
        self.assertEqual(result['q'], [None, 20, 12, 12, 20, 0, 5, 5, 20])

    def test_full_file_requires_explicit_scope(self):
        stages = effective_stages(self.periods, 10, [PowerStage(4, 6, 15)], 15, 'full')
        self.assertEqual(stages, [PowerStage(0, 4, 10),
                                  PowerStage(4, 6, 15), PowerStage(6, 15, 10)])

    def test_gap_invalidates_preexisting_assumption(self):
        ps = derive_estimated_periods(self.times,
                 [event(120, 'HEATING_ON_EST'), event(780, 'HEATING_OFF_EST')],
                 gaps=[(420, 660)])
        self.assertEqual([p.state for p in ps], ['UNKNOWN', 'ON?', 'GAP', 'UNKNOWN', 'OFF?'])
        stages = effective_stages(ps, 10, [], 15)
        self.assertEqual(stages, [PowerStage(2, 7, 10), PowerStage(13, 15, 0)])

    def test_power_increase_marked_and_not_mislabeled_as_off(self):
        ps = derive_estimated_periods(self.times,
             [event(120, 'HEATING_ON_EST'), event(300, 'HEATING_INCREASE_EST'),
              event(600, 'HEATING_OFF_EST')])
        self.assertEqual([p.state for p in ps], ['UNKNOWN', 'ON?', 'P_UP?', 'OFF?'])

    def test_overlapping_manual_overrides_are_rejected(self):
        with self.assertRaises(ValueError):
            effective_stages(self.periods, 10,
                             [PowerStage(2, 4, 10), PowerStage(3, 5, 15)], 15)


if __name__ == '__main__':
    unittest.main()
