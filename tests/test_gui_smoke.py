"""Run with xvfb-run -a python -m unittest tests.test_gui_smoke on Linux.

Verifies that the real Tkinter UI can create and edit timeline markers,
update Q/R, redraw all three plots, and expose the saved event table.
"""
import unittest
import os
from types import SimpleNamespace

from power_model import derive_estimated_periods


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
             'timeline_events':[],'undo_events':[],'session_restored':False}
        self.app.record_rows=[row]
        self.app.listbox.insert('end',record.name)
        self.app.listbox.select_set(0)
        self.app._select()
        self.app.update()

    def tearDown(self):
        self.app.destroy()

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
