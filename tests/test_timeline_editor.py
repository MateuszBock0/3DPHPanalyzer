"""Regression checks for manual marker editing and reliable autosaved sessions."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from timeline_editor import (Transition, validate_transitions, timeline_stages,
                             overlay_stages, resolve_schedule, proposals_from_thermal,
                             snap_to_recorded_sample, last_heating_boundary,
                             ThermalSuggestion, validate_suggestions, initial_suggestions,
                             suggested_heating_events)
from power_model import PowerStage, EstimatedPeriod, calculate
from session_config import export_configuration, validated_import
from session_store import save_session, restore_session, session_path


class InlinePowerTests(unittest.TestCase):
    def test_decimal_comma_and_decimal_dot(self):
        from timeline_gui import parse_inline_q
        self.assertEqual(parse_inline_q('12,5'),12.5)
        self.assertEqual(parse_inline_q(' 20.0 '),20.0)

    def test_empty_power_never_defaults_to_guessed_10_w(self):
        from timeline_gui import parse_inline_q
        for raw in ('', ' ', 'abc', '0', '-10', 'nan', 'inf'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_inline_q(raw)


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.duration=20.
        self.periods=[EstimatedPeriod(0,5,'UNKNOWN'),
                      EstimatedPeriod(5,12,'ON?'),
                      EstimatedPeriod(12,16,'OFF?'),
                      EstimatedPeriod(16,20,'ON?')]

    def test_on_off_change_q_builds_schedule(self):
        ev=[Transition(3,'ON',12),Transition(7,'CHANGE_Q',8),
            Transition(13,'OFF',0),Transition(17,'ON',5)]
        self.assertEqual(timeline_stages(ev,20),
                         [PowerStage(3,7,12),PowerStage(7,13,8),
                          PowerStage(13,17,0),PowerStage(17,20,5)])

    def test_precedence_for_unknown_automatic_manual(self):
        markers=[Transition(6,'ON',10),Transition(14,'OFF',0)]
        st=resolve_schedule(self.periods,20,[PowerStage(7,8,25)],20,
                             transitions=markers)
        self.assertEqual(st,[PowerStage(5,6,20),
                             PowerStage(6,7,10),PowerStage(7,8,25),
                             PowerStage(8,14,10),PowerStage(14,20,0)])
        calculated=calculate([0,360,450,930],[40]*4,st)
        self.assertEqual(calculated['q'],[None,10,25,0])
        self.assertEqual(calculated['r'],[None,4,1.6,None])

    def test_end_is_boundary_but_not_automatic_off(self):
        markers=[Transition(3,'ON',12)]
        self.assertEqual(timeline_stages(markers,20),[PowerStage(3,20,12)])
        self.assertEqual(last_heating_boundary(markers,20),
                         (20,'KONIEC CSV — OFF niepotwierdzone',False))

    def test_explicit_terminal_off_has_no_zero_length_q_segment(self):
        markers=[Transition(3,'ON',12),Transition(20,'OFF',0)]
        self.assertEqual(validate_transitions(markers,20),markers)
        self.assertEqual(timeline_stages(markers,20),[PowerStage(3,20,12)])
        self.assertEqual(last_heating_boundary(markers,20),
                         (20,'OFF (wpis operatora)',True))
        self.assertEqual(resolve_schedule(self.periods,None,[],20,
                         transitions=markers),[PowerStage(3,20,12)])

    def test_only_terminal_off_can_be_at_exact_last_timestamp(self):
        for kind,q in [('ON',10),('CHANGE_Q',5)]:
            with self.assertRaises(ValueError):
                validate_transitions([Transition(20,kind,q)],20)
        with self.assertRaises(ValueError):
            validate_transitions([Transition(20.01,'OFF',0)],20)

    def test_unknown_q_stays_unknown(self):
        self.assertEqual(resolve_schedule(self.periods,None,[],20),[])
        self.assertEqual(resolve_schedule(self.periods,None,[],20,
                         transitions=[Transition(9,'OFF',0)]),
                         [PowerStage(9,20,0)])

    def test_reject_duplicate_and_missing_on_power(self):
        with self.assertRaises(ValueError):
            validate_transitions([Transition(4,'ON',10),Transition(4,'OFF',0)],20)
        with self.assertRaises(ValueError):
            validate_transitions([Transition(4,'ON',None)],20)
        with self.assertRaises(ValueError):
            validate_transitions([Transition(21,'OFF',0)],20)

    def test_proposals_source_is_not_electric_verification(self):
        events=[SimpleNamespace(time=300,kind='HEATING_ON_EST'),
                SimpleNamespace(time=480,kind='HEATING_INCREASE_EST'),
                SimpleNamespace(time=600,kind='HEATING_OFF_EST')]
        transitions=proposals_from_thermal(events,0,20,15)
        self.assertEqual([(e.kind,e.source) for e in transitions],
                         [('ON','accepted_thermal_estimate'),
                          ('OFF','accepted_thermal_estimate')])
        self.assertEqual(timeline_stages(transitions,20),
                         [PowerStage(5,10,15),PowerStage(10,20,0)])
        with self.assertRaises(ValueError):
            proposals_from_thermal(events,0,20,None)

    def test_thermal_proposals_can_be_moved_added_deleted_without_q(self):
        original=[SimpleNamespace(time=300,kind='HEATING_ON_EST'),
                  SimpleNamespace(time=600,kind='HEATING_OFF_EST')]
        proposals=initial_suggestions(original,0,20)
        self.assertEqual([(s.time_min,s.kind,s.source) for s in proposals],
            [(5.,'HEATING_ON_EST','automatic'),(10.,'HEATING_OFF_EST','automatic')])
        changed=validate_suggestions([
            ThermalSuggestion(5.5,'HEATING_ON_EST','operator_adjusted'),
            ThermalSuggestion(10,'HEATING_OFF_EST','automatic'),
            ThermalSuggestion(17,'HEATING_ON_EST','operator_added')],20)
        self.assertEqual([(x.kind,x.time) for x in suggested_heating_events(changed,0)],
                         [(x.kind,60*x.time_min) for x in changed])
        self.assertEqual(len(validate_suggestions(changed[:-1],20)),2)
        with self.assertRaises(ValueError):
            validate_suggestions(changed+[ThermalSuggestion(10,'HEATING_ON_EST')],20)

    def test_accepted_estimated_off_not_falsely_marked_operator(self):
        t=Transition(12,'OFF',0,'accepted_thermal_estimate')
        boundary=last_heating_boundary([t],20)
        self.assertFalse(boundary[2])
        self.assertIn('sugestia',boundary[1])

    def test_snap_rejects_short_and_long_logger_gaps(self):
        for gap in (15,30,60):
            with self.subTest(gap=gap):
                times=list(range(30))+list(range(30+gap, 160+gap))
                target=(29+(gap+1)/2)/60
                with self.assertRaisesRegex(ValueError,'lukę'):
                    snap_to_recorded_sample(target,times)

    def test_snap_to_sample_does_not_jump_across_gap(self):
        times=list(range(0,120,5))+list(range(200,300,5))
        self.assertAlmostEqual(snap_to_recorded_sample(1.01,times),1.)
        with self.assertRaises(ValueError):
            snap_to_recorded_sample(2.7,times)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.t=list(range(601))
        self.record=SimpleNamespace(name='test.csv',origin='in-memory',
             t=self.t,values=[(25.,25.,25.,25.,20.,20.)]*len(self.t))
        self.periods=[EstimatedPeriod(0,10,'ON?')]
        self.timeline=[Transition(1,'ON',12),Transition(5,'OFF',0)]
        self.stages=[PowerStage(2,3,8)]
        self.resolved=resolve_schedule(self.periods,20,self.stages,10,
                                       transitions=self.timeline)
        self.row={'record':self.record,'analysis':SimpleNamespace(delta=[5.]*len(self.t)),
                  'periods':self.periods,'timeline_events':self.timeline,
                  'stages':self.stages,'effective_stages':self.resolved,
                  'constant_q':20.,'constant_scope':'estimated',
                  'cooling_confirmed':False,'ref_enabled':False,
                  'ref_start':0.,'ref_end':4.,
                  'results':calculate(self.t,[5.]*len(self.t),self.resolved)}

    def test_edited_thermal_proposals_survive_json_roundtrip(self):
        edits=[ThermalSuggestion(1.5,'HEATING_ON_EST','operator_adjusted'),
               ThermalSuggestion(8,'HEATING_OFF_EST','operator_added')]
        row=dict(self.row,thermal_suggestions=edits)
        cfg=export_configuration(row)
        self.assertEqual(cfg['schema_version'],5)
        restored=validated_import(cfg,row)
        self.assertEqual(restored['thermal_suggestions'],edits)
        self.assertEqual(restored['periods'][0].state,'UNKNOWN')
        self.assertEqual(restored['periods'][1].state,'ON?')
        old=dict(cfg)
        old.pop('thermal_suggestions')
        old['schema_version']=4
        self.assertEqual(validated_import(old,self.row)['effective_stages'],self.resolved)

    def test_json_roundtrip_for_markers(self):
        data=export_configuration(self.row)
        self.assertEqual(data['schema_version'],5)
        restored=validated_import(data,self.row)
        self.assertEqual(restored['timeline_events'],self.timeline)
        self.assertEqual(restored['effective_stages'],self.resolved)

    def test_atomic_autosave_and_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            target=save_session(self.row,base_dir=temp)
            self.assertTrue(target.exists())
            self.assertEqual(len(list(Path(temp).glob('*.json'))),1)
            empty=dict(self.row,timeline_events=[],stages=[],constant_q=None)
            self.assertTrue(restore_session(empty,base_dir=temp))
            self.assertEqual(empty['timeline_events'],self.timeline)
            self.assertEqual(empty['effective_stages'],self.resolved)
            self.assertEqual(target,session_path(self.record,base_dir=temp))

    def test_autosave_recovers_Q_if_reference_invalidated(self):
        with tempfile.TemporaryDirectory() as temp:
            problematic=dict(self.row,ref_enabled=True,ref_start=4.5,ref_end=6.)
            save_session(problematic,base_dir=temp)
            reloaded=dict(self.row,ref_enabled=False,timeline_events=[],
                          stages=[],constant_q=None)
            self.assertTrue(restore_session(reloaded,base_dir=temp))
            self.assertEqual(reloaded['timeline_events'],self.timeline)
            self.assertFalse(reloaded['ref_enabled'])
            self.assertIn('wyłączono referencję',reloaded['session_restore_note'])

    def test_changed_measurement_never_restores_previous_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            save_session(self.row,base_dir=temp)
            other=SimpleNamespace(name='test.csv',origin='changed',t=self.t,
                values=[(40.,25.,25.,25.,20.,20.)]*len(self.t))
            row2=dict(self.row,record=other,timeline_events=[])
            self.assertFalse(restore_session(row2,base_dir=temp))
            self.assertEqual(row2['timeline_events'],[])

    def test_old_configuration_without_markers_remains_readable(self):
        data=export_configuration(self.row)
        data.pop('timeline_events')
        data['schema_version']=3
        self.assertEqual(validated_import(data,self.row)['timeline_events'],[])


if __name__=='__main__':
    unittest.main()
