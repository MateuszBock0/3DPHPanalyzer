"""Summary dashboard model tests; never fabricate Q, ON or a PHP startup proof."""
import unittest
from types import SimpleNamespace

from power_model import PowerStage, calculate
from timeline_editor import Transition, ThermalSuggestion
from experiment_summary import build_experiment_summary


def fixture(*, episodes=True, power=None, timeline=(), suggestions=(), delta_before=50.,
            delta_during=40., reduction=20., start=300., end=480.):
    t=list(range(601))
    rec=SimpleNamespace(t=t,name='lab_test.csv',origin='memory')
    eps=[SimpleNamespace(display_id='O1',oscillatory=True,start=start,end=end,
                         baseline=delta_before,median_delta=delta_during,
                         reduction_pct=reduction,k2=True)] if episodes else []
    stages=list(power or [])
    calculation=calculate(t,[40.]*len(t),stages)
    return dict(record=rec,
                analysis=SimpleNamespace(record=rec,episodes=eps),
                timeline_events=list(timeline),
                thermal_suggestions=list(suggestions),
                constant_scope='estimated',constant_q=None,stages=[],
                effective_stages=stages,results=calculation,
                cooling_confirmed=False,
                k2_reviews={'O1':SimpleNamespace(label='K2: Q niepewna')} if eps else {},
                activity_assessments={'O1':SimpleNamespace(label='Możliwa aktywność')} if eps else {})


class SummaryModelTests(unittest.TestCase):
    def test_missing_power_and_on_do_not_turn_csv_start_into_startup(self):
        overview=build_experiment_summary(fixture())
        self.assertEqual(overview.first_min,5.)
        self.assertIsNone(overview.first_from_on_min)
        self.assertIn('Nieznany',overview.on_provenance)
        self.assertEqual(overview.q_display,'Q nieznana')
        self.assertEqual(overview.r_display,'—')
        self.assertEqual(overview.delta_display,'+20.0%')
        self.assertEqual(overview.episodes[0].ident,'O1')

    def test_operator_on_preferred_over_thermal_suggestion(self):
        overview=build_experiment_summary(fixture(
            power=[PowerStage(2,10,20)],
            timeline=[Transition(2,'ON',20,'operator')],
            suggestions=[ThermalSuggestion(1,'HEATING_ON_EST')]))
        self.assertEqual(overview.first_from_on_min,3.)
        self.assertIn('operatora',overview.on_provenance)
        self.assertIn('20 W',overview.q_display)
        self.assertAlmostEqual(float(overview.r_display.split()[0]),2.)
        self.assertIn('przejściowego',overview.r_detail)

    def test_estimated_on_is_not_called_confirmed(self):
        overview=build_experiment_summary(fixture(
            suggestions=[ThermalSuggestion(2.5,'HEATING_ON_EST',
                                           'operator_adjusted')]))
        self.assertEqual(overview.first_from_on_min,2.5)
        self.assertIn('szacunek',overview.on_provenance)
        self.assertEqual(overview.episodes[0].delta_before_k,50.)

    def test_off_cancels_previous_on_and_blocks_resurrection(self):
        overview=build_experiment_summary(fixture(
            timeline=[Transition(1,'ON',10),Transition(4,'OFF',0)],
            suggestions=[ThermalSuggestion(2,'HEATING_ON_EST')]))
        self.assertIsNone(overview.first_from_on_min)
        self.assertIn('Brak ON',overview.on_provenance)

    def test_power_change_during_episode_disables_single_resistance(self):
        overview=build_experiment_summary(fixture(
            power=[PowerStage(0,6,10),PowerStage(6,10,20)]))
        self.assertEqual(overview.r_display,'—')
        self.assertIn('Zmiana Q',overview.r_detail)
        self.assertIn('10 / 20 W',overview.q_display)

    def test_no_episodes_no_false_startup(self):
        overview=build_experiment_summary(fixture(episodes=False))
        self.assertEqual(overview.count,0)
        self.assertIsNone(overview.first_id)
        self.assertIsNone(overview.first_from_on_min)
        self.assertEqual(overview.delta_display,'—')
        self.assertEqual(overview.r_display,'—')
        self.assertEqual(overview.episodes,())

    def test_no_reduction_reference_is_not_fabricated(self):
        overview=build_experiment_summary(fixture(
            delta_before=None,reduction=None))
        self.assertEqual(overview.delta_display,'—')
        self.assertIn('Brak wiarygodnej',overview.delta_detail)

    def test_thermal_off_cancels_inferred_on(self):
        overview=build_experiment_summary(fixture(
            suggestions=[ThermalSuggestion(1,'HEATING_ON_EST'),
                         ThermalSuggestion(4,'HEATING_OFF_EST')]))
        self.assertIsNone(overview.first_from_on_min)


if __name__=='__main__':
    unittest.main()
