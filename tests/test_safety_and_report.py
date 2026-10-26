"""Regression tests for safe reference, P_UP, JSON, and HTML methodology."""
import unittest
from types import SimpleNamespace
from power_model import PowerStage, calculate, derive_estimated_periods, effective_stages
from session_config import validated_import, export_configuration, LegacyConfigurationError

class StrictReferenceTests(unittest.TestCase):
    def test_off_cannot_be_skipped_by_filtering_valid_R(self):
        ts = list(range(1801))
        steps = [PowerStage(0,10,10),PowerStage(10,20,0),PowerStage(20,30,10)]
        out=calculate(ts,[50.]*len(ts),steps,(0,30))
        self.assertIsNone(out['r_ref'])
        self.assertIn('JEDNYM',out['reference_error'])

    def test_unknown_q_breaks_reference(self):
        ts=list(range(1801))
        out=calculate(ts,[50.]*len(ts),
                      [PowerStage(0,10,10),PowerStage(20,30,10)],(0,30))
        self.assertIsNotNone(out['reference_error'])

    def test_logger_gap_breaks_reference(self):
        ts=list(range(60))+list(range(180,241))
        out=calculate(ts,[40.]*len(ts),[PowerStage(0,5,10)],(0,4))
        self.assertIn('lukę',out['reference_error'])

    def test_contiguous_reference(self):
        ts=list(range(300))
        out=calculate(ts,[30.]*len(ts),[PowerStage(0,5,10)],(0,4))
        self.assertIsNone(out['reference_error'])
        self.assertAlmostEqual(out['r_ref'],3.)
        self.assertEqual(out['relative'][3],1.)

    def test_outside_recording_rejected(self):
        out=calculate(list(range(20)),[30.]*20,[PowerStage(0,1,10)],(0,5))
        self.assertIsNotNone(out['reference_error'])

    def test_power_increase_unassigned_unless_manual(self):
        times=list(range(901))
        ev=[SimpleNamespace(time=120,kind='HEATING_ON_EST'),
            SimpleNamespace(time=420,kind='HEATING_INCREASE_EST'),
            SimpleNamespace(time=600,kind='HEATING_OFF_EST')]
        periods=derive_estimated_periods(times,ev)
        stages=effective_stages(periods,20,[],15)
        out=calculate([0,180,450,660],[40.]*4,stages)
        self.assertEqual(out['q'],[None,20,None,0])
        stages=effective_stages(periods,20,[PowerStage(7,10,30)],15)
        out=calculate([0,180,450,660],[40.]*4,stages)
        self.assertEqual(out['q'],[None,20,30,0])

class QuasiSteadyReferenceTests(unittest.TestCase):
    def test_quiet_temperatures_allow_reference(self):
        times=list(range(601))
        stages=[PowerStage(0,10,20)]
        result=calculate(times,[40.]*601,stages,(2,6),
                         te=[80.]*601,tc=[40.]*601)
        self.assertIsNone(result['reference_error'])
        self.assertAlmostEqual(result['r_ref'],2.)

    def test_warmup_drift_rejected_by_desktop(self):
        times=list(range(601))
        te=[40.+.05*i for i in times]  # 3 °C/min warmup
        tc=[25.]*601
        result=calculate(times,[x-25 for x in te],[PowerStage(0,10,20)],
                         (2,6),te=te,tc=tc)
        self.assertIsNone(result['r_ref'])
        self.assertIn('trend Te/Tc',result['reference_error'])

    def test_short_reference_requires_at_least_120_seconds(self):
        times=list(range(601))
        result=calculate(times,[40.]*601,[PowerStage(0,10,20)],
                         (2,3),te=[80.]*601,tc=[40.]*601)
        self.assertIsNone(result['r_ref'])
        self.assertIn('120 s',result['reference_error'])


class ConfigTests(unittest.TestCase):
    def setUp(self):
        ts=list(range(601))
        values=[(50.,51.,40.,40.,30.,30.) for _ in ts]
        self.record=SimpleNamespace(name='sample.csv',origin='original',
                                    t=ts,values=values)
        stages=[PowerStage(0,8,10)]
        self.row=dict(record=self.record,
                      analysis=SimpleNamespace(delta=[20.]*len(ts)),
                      stages=stages,periods=[],constant_q=None,constant_scope='estimated',
                      effective_stages=stages,ref_enabled=True,ref_start=1.,ref_end=4.,
                      results=calculate(ts,[20.]*len(ts),stages,(1,4)))

    def test_roundtrip_and_dataset_fingerprint(self):
        config=export_configuration(self.row)
        self.assertEqual(validated_import(config,self.row)['stages'],[PowerStage(0,8,10)])
        self.record.values[0]=(100.,101.,40.,40.,30.,30.)
        with self.assertRaisesRegex(ValueError,'nie pasuje'):
            validated_import(config,self.row)

    def test_legacy_json_requires_consent(self):
        config=export_configuration(self.row)
        del config['source_identity']
        with self.assertRaises(LegacyConfigurationError):
            validated_import(config,self.row)
        self.assertTrue(validated_import(config,self.row,legacy_confirmed=True)['ref_enabled'])

    def test_invalid_window_rejected_before_mutating_row(self):
        config=export_configuration(self.row)
        config['manual_overrides']=[{'start_min':0,'end_min':2,'q_w':10},
                                    {'start_min':2,'end_min':4,'q_w':0}]
        with self.assertRaisesRegex(ValueError,'JEDNYM'):
            validated_import(config,self.row)
        self.assertEqual(self.row['stages'],[PowerStage(0,8,10)])

    def test_html_contains_last_methodology_section(self):
        import php_analyzer as engine
        import methodology
        page=engine.render_html([],[],[],{},[],[],desktop_mode=True,
             panel_label='R_app [K/W]',methodology_html=methodology.as_html(embedded=True))
        self.assertIn('R_app [K/W]',page)
        self.assertIn('id="metodyka"',page)
        self.assertLess(page.index('Legenda wyników'),page.index('id="metodyka"'))

if __name__=='__main__':
    unittest.main()
