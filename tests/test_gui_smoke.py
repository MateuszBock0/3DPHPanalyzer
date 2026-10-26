"""Run with xvfb-run -a python -m unittest tests.test_gui_smoke on Linux.

Verifies that the real Tkinter UI can create and edit timeline markers,
update Q/R, redraw all three plots, and expose the saved event table.
"""
import unittest
import os
from types import SimpleNamespace

from power_model import derive_estimated_periods, PowerStage
from timeline_editor import initial_suggestions, ThermalSuggestion


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt',
                     'Tkinter requires a desktop display or xvfb-run')
class DesktopTimelineSmokeTests(unittest.TestCase):
    def setUp(self):
        import php_desktop as desktop
        self.app=desktop.PHPDesktop()
        self.app.withdraw()
        self.app._first_q_dialog_done=True
        self.app._autosave_current=lambda: None
        t=list(range(180))
        vals=[(40.,41.,34.,34.,29.,29.) for _ in t]
        record=desktop.engine.Record('synthetic.csv','fixture',t,vals)
        analysis=desktop.engine.analyze(record)
        row={'record':record,'analysis':analysis,'stages':[],
             'results':None,'periods':derive_estimated_periods(t,analysis.heating_events),
             'constant_q':None,'constant_scope':'estimated',
             'effective_stages':[],'ref_enabled':False,
             'ref_start':0.,'ref_end':2.,'cooling_confirmed':False,
             'k2_reviews':{},'activity_assessments':{},
             'timeline_events':[],
             'thermal_suggestions':initial_suggestions(
                 analysis.heating_events,t[0],(t[-1]-t[0])/60),
             'undo_events':[],'session_restored':False}
        self.app.record_rows=[row]
        self.app.listbox.insert('end',record.name)
        self.app.listbox.select_set(0)
        self.app._select()
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def test_summary_tab_opens_after_csv_selection_and_updates_with_Q(self):
        self.assertEqual(self.app.tabs.select(), str(self.app.summary_page))
        self.assertEqual(self.app.summary_filename.get(),'synthetic.csv')
        self.assertIn('nieznana',self.app.summary_card_vars['q'][0].get())
        self.assertEqual(self.app.summary_card_vars['r'][0].get(),'—')
        self.app.editor_q_var.set('15')
        self.app._add_marker('ON',.5)
        self.assertIn('15 W',self.app.summary_card_vars['q'][0].get())
        self.assertEqual(self.app.tabs.select(),str(self.app.summary_page))

    def test_summary_episode_table_and_click_to_zoom(self):
        from types import SimpleNamespace
        record=self.app._get()['record']
        episode=SimpleNamespace(display_id='O1',oscillatory=True,
            start=70.,end=110.,baseline=13.,median_delta=10.,
            reduction_pct=23.,k2=False)
        self.app._get()['analysis'].episodes=[episode]
        self.app._render_summary()
        self.assertEqual(self.app.summary_tree.get_children(),('O1',))
        self.assertIn('23',self.app.summary_card_vars['delta'][0].get())
        self.app._timeline_open_episode('O1')
        self.assertEqual(self.app.tabs.select(),str(self.app.chart_page))
        left,right=self.app.axes[-1].get_xlim()
        self.assertLess(left,70/60)
        self.assertGreater(right,110/60)

    def test_inline_q_and_terminal_off(self):
        from timeline_editor import timeline_stages
        from power_model import PowerStage
        self.assertEqual(self.app.editor_q_var.get(), '')
        self.app.editor_q_var.set('12,5')
        self.assertTrue(self.app._add_marker('ON',.5))
        self.assertAlmostEqual(self.app._get()['results']['q'][60],12.5)
        duration=(self.app._get()['record'].t[-1]-self.app._get()['record'].t[0])/60
        self.assertTrue(self.app._add_marker('OFF',duration))
        self.assertEqual(
            timeline_stages(self.app._get()['timeline_events'],duration),
            [PowerStage(.5,duration,12.5)])
        self.assertEqual(len(self.app._manual_line_artists),2)
        self.app.update()

    def test_thermal_suggestion_drag_add_delete_undo_no_Q_needed(self):
        self.assertEqual(self.app.editor_q_var.get(),'')
        self.app._add_suggestion('HEATING_ON_EST',.65)
        self.app._add_suggestion('HEATING_OFF_EST',1.65)
        self.assertEqual(len(self.app._get()['thermal_suggestions']),2)
        self.assertEqual(len(self.app.suggestion_tree.get_children()),2)
        self.assertEqual(self.app._get()['periods'][1].state,'ON?')
        self.assertEqual(self.app._get()['results']['q'][60],None)
        axis=self.app.axes[0]
        x=axis.transData.transform((.65,0))[0]
        press=SimpleNamespace(button=1,x=x,xdata=.65,inaxes=axis)
        self.app._on_chart_press(press)
        self.assertEqual(self.app._drag_suggestion_index,0)
        self.app._on_chart_release(SimpleNamespace(button=1,x=x+10,xdata=.75,inaxes=axis))
        self.assertAlmostEqual(self.app._get()['thermal_suggestions'][0].time_min,.75)
        self.assertEqual(self.app._get()['thermal_suggestions'][0].source,'operator_adjusted')
        self.app._delete_suggestion(1)
        self.assertEqual(len(self.app._get()['thermal_suggestions']),1)
        self.app.undo_timeline()
        self.assertEqual(len(self.app._get()['thermal_suggestions']),2)
        self.app.reset_thermal_suggestions()
        self.assertEqual(len(self.app._get()['thermal_suggestions']),0)

    def test_distinct_export_names_preserve_original_config(self):
        original=self.app._get()
        second=dict(original)
        from copy import copy
        second_record=copy(original['record'])
        second_record.origin='another/folder/synthetic.csv'
        second['record']=second_record
        a=self.app._export_view(original)
        b=self.app._export_view(second)
        self.assertNotEqual(a['record'].name,b['record'].name)
        self.assertEqual(original['record'].name,'synthetic.csv')
        self.assertEqual(a['_original_row']['record'].name,'synthetic.csv')

    def test_reject_manual_Q_stage_beyond_record(self):
        from unittest.mock import patch
        duration=self.app._duration_min()
        with patch('php_desktop.messagebox.showerror'):
            self.app._add_override(PowerStage(0,duration+5,10))
        self.assertEqual(self.app._get()['stages'],[])

    def test_plot_zoom_retained_after_timeline_edit(self):
        self.app.axes[-1].set_xlim(.25,.9)
        self.app.editor_q_var.set('10')
        self.app._add_marker('ON',.5)
        left,right=self.app.axes[-1].get_xlim()
        self.assertAlmostEqual(left,.25)
        self.assertAlmostEqual(right,.9)

    def test_manual_on_off_redraw_table_and_undo(self):
        self.app.editor_q_var.set('10')
        self.app._add_marker('ON',.5)
        self.app._add_marker('OFF',1.5)
        self.assertEqual(len(self.app._get()['timeline_events']),2)
        self.assertEqual(len(self.app.timeline_tree.get_children()),2)
        self.assertEqual(self.app._get()['results']['q'][60],10.)
        self.assertEqual(self.app._get()['results']['q'][100],0.)
        self.assertEqual(len(self.app._manual_line_artists),2)
        self.app._move_transition(1,1.75)
        self.assertEqual(self.app._get()['results']['q'][100],10.)
        self.app.undo_timeline()
        self.assertEqual(self.app._get()['results']['q'][100],0.)
        self.app.update()


if __name__=='__main__':
    unittest.main()
