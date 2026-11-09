"""TESTS_NO_PCM scanner, temperature correction and U/I diary integration."""
import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

import php_analyzer as engine
from bulk_inputs import input_files, deduplicate_files
from power_diary import read_diary
from thermal_quality import (transform_record, assess_quality,
                             COEFFICIENTS, FIT_RANGE_C)


def fake_picolog(n=150):
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['',*[f'Kanał {ch} Ostatni (C)' for ch in (1,3,4,5,6,7)]])
    for t in range(n):
        writer.writerow([t,80,82,-73.6,50,40,72])
    return output.getvalue().encode('utf-8')


class FolderImportTests(unittest.TestCase):
    def test_large_folder_ignores_derived_results_zip_and_auxiliary_csv(self):
        raw=fake_picolog()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'TESTS_NO_PCM'
            root.mkdir()
            (root/'test-3_11.csv').write_bytes(raw)
            (root/'drut(Arkusz1).csv').write_text('U;I;opis\n10;2;20 W',encoding='utf8')
            (root/'zestawienie-wykresy.csv').write_text('t_id_1=1.1*t',encoding='utf8')
            results=root/'Results'/'przebiegi'
            results.mkdir(parents=True)
            (results/'test-3_11_przebieg.csv').write_bytes(raw)
            (root/'day_2').mkdir()
            (root/'day_2'/'same_measurement.csv').write_bytes(raw)
            with zipfile.ZipFile(root/'Nowy folder.zip','w') as archive:
                archive.writestr('test_copy.csv',raw)
            records=input_files(root)
            self.assertEqual(len(records),2)
            self.assertEqual(set(n for n,_,_ in records),
                             {'test-3_11.csv','same_measurement.csv'})
            unique,dups=deduplicate_files(records)
            self.assertEqual(len(unique),1)
            self.assertEqual(len(dups),1)
            # An explicit ZIP remains supported; unlike one hidden in folder.
            self.assertEqual(len(input_files(root/'Nowy folder.zip')),1)

    def test_no_external_results_and_non_picolog_csv_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'TESTS_NO_PCM'
            root.mkdir()
            (root/'Results').mkdir()
            (root/'Results'/'fake.csv').write_bytes(fake_picolog())
            self.assertEqual(input_files(root),[])


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.record=engine.Record('test.csv','local',list(range(150)),
            [(80.,82.,-73.6,50.,40.,72.)]*150)

    def test_calibration_is_not_automatic_or_destructive(self):
        raw,_=transform_record(self.record,False)
        self.assertEqual(raw.values[0][0],80)
        processed,warnings=transform_record(self.record,True)
        a,b=COEFFICIENTS[1]
        self.assertAlmostEqual(processed.values[0][0],a*80+b)
        self.assertEqual(self.record.values[0][0],80)
        self.assertEqual(self.record.values[0][2],-73.6)
        self.assertEqual(processed.t,self.record.t)
        self.assertTrue(any('TP4:' in x and 'EKSTRAPOLACJ' in x for x in warnings))
        self.assertEqual(FIT_RANGE_C,(20.,105.))

    def test_tp4_exclusion_replaces_tm_only_without_hiding_raw(self):
        corrected,_=transform_record(self.record,True)
        a=engine.analyze(corrected,exclude_tp4=True)
        b=engine.analyze(corrected)
        self.assertAlmostEqual(a.tm[20],corrected.values[20][3])
        self.assertNotAlmostEqual(a.tm[20],b.tm[20])
        self.assertEqual(a.te,b.te)
        self.assertEqual(a.tc,b.tc)
        self.assertEqual(a.delta,b.delta)
        self.assertIn('TP4',str(a.notes))

    def test_quality_flags_tp4_and_condenser_split(self):
        assessment=assess_quality(self.record)
        self.assertTrue(assessment.suspect_tp4)
        self.assertAlmostEqual(assessment.condenser_median_difference_c,32.)
        self.assertTrue(any('TP6–TP7' in x for x in assessment.notes))


class DiaryTests(unittest.TestCase):
    def test_only_u_times_i_from_drut_not_wire_nominal_power(self):
        rows=[['']*26 for _ in range(6)]
        rows[0][4]='godzina ustawienia'
        rows[0][7]='ustawione napięcie [V]'
        rows[0][8]='natężenie odczytane A'
        rows[1][4]='09:37';rows[1][7]='10,5';rows[1][8]='1,25'
        rows[1][9]='11,9';rows[1][10]='12,0'
        rows[2][4]='10:00';rows[2][7]='12';rows[2][8]='1,8'
        out=io.StringIO()
        csv.writer(out,delimiter=';').writerows(rows)
        points=read_diary(out.getvalue().encode('utf-8'), 'drut.csv')
        self.assertEqual(len(points),2)
        self.assertAlmostEqual(points[0].power_w,13.125)
        self.assertAlmostEqual(points[1].power_w,21.6)
        self.assertEqual(points[0].time_label,'09:37')

    def test_reject_arbitrary_tables_without_voltage_current_headers(self):
        with self.assertRaises(ValueError):
            read_diary(b'Q;R;something\n10;2;20')


if __name__=='__main__':
    unittest.main()
