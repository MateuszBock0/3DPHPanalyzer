"""Regression tests for post-hoc K2 qualification, final Q and midnight rolls."""
import unittest
from types import SimpleNamespace

import php_analyzer as engine
from episode_validation import (resolved_q_label, stable_positive_power,
                                qualify_episode_k2)
from power_model import PowerStage


def assessment_record(gap=False):
    times = [float(x) for x in range(0, 1801, 5)
             if not gap or not 1010 <= x <= 1130]
    record = SimpleNamespace(t=times)
    ep = SimpleNamespace(display_id='O1', start=600., end=1200.,
                         oscillatory=True, k2=True)
    return SimpleNamespace(record=record), ep


class K2QualityTests(unittest.TestCase):
    def test_no_q_does_not_confirm_k2(self):
        a, ep = assessment_record()
        self.assertEqual(qualify_episode_k2(a, ep, []).code, 'K2_Q_NIEPEWNA')

    def test_q_changed_rejects_k2(self):
        a, ep = assessment_record()
        stages = [PowerStage(0, 12, 10), PowerStage(12, 31, 20)]
        self.assertEqual(qualify_episode_k2(a, ep, stages, True).code, 'K2_Q_NIEPEWNA')

    def test_constant_q_without_cooling_confirmation_is_not_green(self):
        a, ep = assessment_record()
        s = [PowerStage(0, 31, 10)]
        self.assertEqual(qualify_episode_k2(a, ep, s).code, 'K2_CHLODZENIE_NIEZNANE')

    def test_constant_q_and_operator_cooling_declaration_is_conditional(self):
        a, ep = assessment_record()
        s = [PowerStage(0, 31, 10)]
        r = qualify_episode_k2(a, ep, s, True)
        self.assertEqual(r.code, 'K2_WARUNKOWE')
        self.assertEqual(r.q_w, 10)

    def test_logger_gap_blocks_confirmation(self):
        a, ep = assessment_record(gap=True)
        self.assertEqual(qualify_episode_k2(a, ep, [PowerStage(0, 31, 10)], True).code, 'K2_LUKA')

    def test_off_and_unknown_block_constant_q(self):
        s = [PowerStage(0, 4, 10), PowerStage(4, 7, 0), PowerStage(7, 31, 10)]
        self.assertIsNone(stable_positive_power(s, 3, 21)[0])
        self.assertIsNone(stable_positive_power([PowerStage(0, 8, 10)], 3, 21)[0])

    def test_k1_without_thermal_k2_does_not_get_conditional_k2(self):
        a, ep = assessment_record()
        ep.k2 = False
        self.assertEqual(qualify_episode_k2(a, ep, [PowerStage(0, 31, 10)], True).code, 'K1_TYLKO')

    def test_resolved_q_description_includes_manual_change(self):
        s = [PowerStage(0, 2, 10), PowerStage(2, 3, 8), PowerStage(3, 5, 10)]
        self.assertEqual(resolved_q_label(s, 0, 5), 'Q zmienna: 8, 10 W')
        self.assertEqual(resolved_q_label([PowerStage(0, 2, 10)], 0, 5),
                         'Q częściowo nieznana; znane: 10 W')
        self.assertEqual(resolved_q_label([], 0, 5), 'Q nieznana')


class TimeAndExportTests(unittest.TestCase):
    def test_two_midnight_rollovers(self):
        raw = [23*3600+59*60+59, 1, 3600, 23*3600+59*60+59, 1]
        unwrapped = engine.unwrap_midnight_clock(raw)
        self.assertTrue(all(a < b for a, b in zip(unwrapped, unwrapped[1:])))
        self.assertEqual(unwrapped[-1], 2*86400+1)

    def test_non_midnight_backwards_is_not_a_new_day(self):
        self.assertEqual(engine.unwrap_midnight_clock([36000, 35000, 37000]),
                         [36000, 35000, 37000])

    def test_parse_csv_midnight_chronology(self):
        header = 'Time,Channel 1,Channel 3,Channel 4,Channel 5,Channel 6,Channel 7'
        records = [header]
        for i in range(130):
            sec = (23*3600 + 59*60 + 40 + i) % 86400
            hour, rem = divmod(sec, 3600)
            minute, second = divmod(rem, 60)
            records.append(f'{hour:02d}:{minute:02d}:{second:02d},30,30,28,28,25,25')
        rec = engine.parse_csv(('\n'.join(records)).encode(), 'midnight.csv', 'fixture')
        self.assertEqual(len(rec.t), 130)
        self.assertEqual(rec.t[-1] - rec.t[0], 129)

    def test_separate_oscillatory_and_all_thermal_events(self):
        record = SimpleNamespace(name='fixture.csv', fragment_of='')
        common = dict(start=300., end=420., from_heating_on_s=None,
                      peaks=4, troughs=4, t_ev=70., t_middle=50.,
                      t_co=40., baseline=30., median_delta=20.,
                      reduction_pct=33., improvement_duration_s=320.,
                      rms_max=2., pair_corr=0.5, kind='OSC_ONLY')
        o = SimpleNamespace(display_id='O1', oscillatory=True, k2=False, **common)
        t = SimpleNamespace(display_id='T1', oscillatory=False, k2=False, **common)
        analysis = SimpleNamespace(record=record, episodes=[o, t])
        self.assertEqual(len(engine.csv_episodes([analysis])), 2)
        filtered = engine.csv_episodes([analysis], oscillatory_only=True)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['epizod'], 'O1')


if __name__ == '__main__':
    unittest.main()
