"""Tests of explainable wall-temperature evidence for possible PHP activity."""
import unittest
from types import SimpleNamespace

from power_model import PowerStage
from activity_assessment import assess_episode, assess_all


def fixture(mode='opposite', gap=False, spike=False, k2=True):
    times = list(range(0, 1000))
    if gap:
        times = [t for t in times if not (175 < t < 240)]
    te, tc, values = [], [], []
    for t in times:
        if mode == 'opposite':
            frac = min(1.0, max(0, (t-450)/60))
            e, c = 120.-10*frac, 50.+8*frac
        else:
            frac = min(1.0, max(0, (t-450)/60))
            e, c = 120.+10*frac, 50.+8*frac
        if spike and t == 500:
            e += 7.0
        te.append(e); tc.append(c)
        values.append((e,e,75.,75.,c,c))
    rec = SimpleNamespace(t=times, values=values, name='sample.csv')
    analysis = SimpleNamespace(record=rec, te=te, tc=tc,
                               episodes=[], delta=[a-b for a,b in zip(te,tc)])
    ep = SimpleNamespace(start=450.,end=840.,oscillatory=True,k2=k2,display_id='O1')
    analysis.episodes=[ep]
    return analysis,ep


class ActivityAssessmentTests(unittest.TestCase):
    def test_concordant_signals_with_manual_q_and_cooling_are_strong_clues(self):
        a,ep=fixture()
        st=[PowerStage(0,16,20)]
        r=assess_episode(a,ep,st,st,cooling_confirmed=True)
        self.assertEqual(r.code,'SILNE_PRZESLANKI')
        self.assertLess(r.dte_c,-1)
        self.assertGreater(r.dtc_c,.5)
        self.assertLess(r.ddelta_k,0)

    def test_k1_and_k2_without_q_are_only_possible(self):
        a,ep=fixture()
        r=assess_episode(a,ep,[])
        self.assertEqual(r.code,'MOZLIWA_AKTYWNOSC')
        self.assertIn('Wpisz',r.to_enter)

    def test_automatic_on_assumption_is_not_verified_power(self):
        a,ep=fixture()
        r=assess_episode(a,ep,[PowerStage(0,16,20)],
                         cooling_confirmed=True)
        self.assertEqual(r.code,'MOZLIWA_AKTYWNOSC')
        self.assertEqual(r.power_source,'Q przypisana wg ON?')

    def test_missing_cooling_confirmation_blocks_strong_grade(self):
        a,ep=fixture()
        stages=[PowerStage(0,16,20)]
        r=assess_episode(a,ep,stages,stages,cooling_confirmed=False)
        self.assertEqual(r.code,'MOZLIWA_AKTYWNOSC')

    def test_direction_mismatch_with_no_k2_is_ambiguous(self):
        a,ep=fixture(mode='both_warm',k2=False)
        r=assess_episode(a,ep,[])
        self.assertEqual(r.code,'NIEJEDNOZNACZNE')

    def test_changed_power_cannot_be_called_strong(self):
        a,ep=fixture()
        st=[PowerStage(0,7,10),PowerStage(7,16,20)]
        r=assess_episode(a,ep,st,st,cooling_confirmed=True)
        self.assertEqual(r.code,'NIEJEDNOZNACZNE')

    def test_logger_gap_and_sensor_spike_block_strong(self):
        stages=[PowerStage(0,16,20)]
        a,ep=fixture(gap=True)
        r=assess_episode(a,ep,stages,stages,cooling_confirmed=True)
        self.assertEqual(r.code,'NIEJEDNOZNACZNE')
        a,ep=fixture(spike=True)
        r=assess_episode(a,ep,stages,stages,cooling_confirmed=True)
        self.assertEqual(r.code,'NIEJEDNOZNACZNE')

    def test_full_file_declared_q_counted_but_not_flow_proof(self):
        a,ep=fixture()
        stages=[PowerStage(0,16,20)]
        r=assess_all(a,stages,constant_q=20,constant_scope='full',
                     cooling_confirmed=True)['O1']
        self.assertEqual(r.code,'SILNE_PRZESLANKI')
        self.assertIn('Bez bezpośredniego',r.summary)


if __name__ == '__main__':
    unittest.main()
