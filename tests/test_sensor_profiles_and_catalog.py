"""Regression tests for November 2026 thermal calibration, QA, diary and folder structure."""
from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import dataset_catalog
import php_analyzer as engine
import sensor_profiles
from power_model import PowerStage, calculate
from session_config import export_configuration, validated_import
from timeline_editor import initial_suggestions


def csv_bytes(n=180, bad4=False):
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['',*[f'Kanał {ch} Ostatni (C)'
                            for ch in sensor_profiles.CHANNELS]])
    for i in range(n):
        values=[160.,161.,-73. if bad4 and i==80 else 100.,
                101.,84.,118.]
        writer.writerow([f'00:{i//60:02d}:{i%60:02d}',*values])
    return output.getvalue().encode('utf-8')


class DatasetCatalogTests(unittest.TestCase):
    def test_real_folder_layout_skips_outputs_and_notes_and_reads_zip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'TESTS_NO_PCM'
            root.mkdir()
            (root/'Results'/'przebiegi').mkdir(parents=True)
            (root/'Results'/'przebiegi'/'test-12_10_przebieg.csv').write_bytes(csv_bytes())
            (root/'drut(Arkusz1).csv').write_text('data;U;I\n',encoding='utf8')
            (root/'zestawienie-wykresy(Arkusz1).csv').write_text(
                't_id_1=...;kalibracja',encoding='utf8')
            (root/'test-12_10.csv').write_bytes(csv_bytes())
            (root/'app'/'_internal').mkdir(parents=True)
            (root/'app'/'_internal'/'fake.csv').write_bytes(csv_bytes())
            with zipfile.ZipFile(root/'Nowy folder.zip','w') as z:
                z.writestr('nested/3_11-short.csv',csv_bytes(180))
                z.writestr('nested/3_11-long.csv',csv_bytes(240))
                z.writestr('nested/Results/not_a_test.csv',csv_bytes(240))
            found=dataset_catalog.input_files(root)
            self.assertEqual(len(found),2)  # raw+short identical; long is distinct
            self.assertEqual({x[0] for x in found},
                             {'test-12_10.csv','3_11-long.csv'})
            recs, errors=engine.unique_records(found)
            self.assertEqual(len(recs),2)
            self.assertEqual(errors,[])

    def test_non_matching_csv_never_parses_as_pico(self):
        self.assertFalse(dataset_catalog.picolog_header(
            b'index;U;I\n1;12.12;1.82\n'))
        self.assertTrue(dataset_catalog.picolog_header(csv_bytes()))

    def test_exact_prefix_not_just_matching_probes(self):
        base=csv_bytes(180)
        long=csv_bytes(240)
        r1=engine.parse_csv(base,'short.csv','a')
        r2=engine.parse_csv(long,'long.csv','b')
        assert r1.t==r2.t[:len(r1.t)]
        recs,_=engine.unique_records([
            ('short.csv','a',base),('long.csv','b',long)])
        self.assertEqual(recs[0].fragment_of,'long.csv')
        # An internal change cannot pass as a true prefix.
        tampered=long.replace(b'00:01:25,160.0',b'00:01:25,159.0')
        recs,_=engine.unique_records([
            ('short.csv','a',base),('long.csv','b',tampered)])
        self.assertEqual(recs[0].fragment_of,'')


class ThermocoupleTests(unittest.TestCase):
    def setUp(self):
        self.raw=engine.parse_csv(csv_bytes(180,bad4=True),'lab.csv','memory')

    def test_correction_is_linear_and_non_mutating(self):
        before=self.raw.values[0]
        first=sensor_profiles.process_record(self.raw,'corrected')
        second=sensor_profiles.process_record(self.raw,'corrected')
        self.assertEqual(first.values,second.values)
        self.assertEqual(self.raw.values[0],before)
        self.assertAlmostEqual(first.values[0][0],
            .990584654516796*160-.670008747930264,places=8)
        self.assertNotEqual(first.values[0],before)

    def test_quality_warns_outside_fit_and_bad_t4(self):
        quality=sensor_profiles.quality_report(self.raw,'corrected',True)
        self.assertEqual(dict(quality.extrapolated)[1],180)
        self.assertEqual(quality.ch4_outliers,1)
        self.assertEqual(quality.condenser_disagreement,180)
        self.assertTrue(any('EKSTRAPOLACJA' in x for x in quality.notes()))

    def test_exclude_t4_mean_means_t5_only_without_fabrication(self):
        standard=engine.analyze(self.raw)
        masked=engine.analyze(self.raw,exclude_thermocouple4=True)
        self.assertNotEqual(standard.tm[80],masked.tm[80])
        self.assertEqual(masked.tm[80],self.raw.values[80][3])
        self.assertEqual(standard.delta,masked.delta)
        self.assertEqual(standard.te,masked.te)

    def test_session_calibration_roundtrip_keeps_identity_raw(self):
        analysis=engine.analyze(self.raw)
        duration=(self.raw.t[-1]-self.raw.t[0])/60
        stages=[PowerStage(0,duration,22)]
        row={'record':self.raw,'analysis':analysis,'results':calculate(self.raw.t,
             analysis.delta,stages),
             'stages':stages,'periods':[],
             'constant_q':None,'constant_scope':'estimated',
             'thermal_suggestions':[],
             'effective_stages':stages,
             'ref_enabled':False,'ref_start':0,'ref_end':2,
             'cooling_confirmed':False,'timeline_events':[],
             'calibration_mode':'corrected','exclude_thermocouple4':True,
             'power_evidence':[dict(start_min=0,end_min=duration,
                 voltage_v=11,current_a=2,power_w=22,
                 source='drut test row',note='punktowy')]}
        exported=export_configuration(row)
        self.assertEqual(exported['schema_version'],6)
        recovered=validated_import(json.loads(json.dumps(exported)),row)
        self.assertEqual(recovered['calibration_mode'],'corrected')
        self.assertTrue(recovered['exclude_thermocouple4'])
        self.assertAlmostEqual(recovered['analysis'].record.values[0][0],
            sensor_profiles.COEFFS[1][0]*160+sensor_profiles.COEFFS[1][1])
        self.assertEqual(recovered['power_evidence'][0]['power_w'],22.)
        self.assertEqual(row['record'].values[0][0],160.)

    def test_diary_only_candidates_not_fake_csv_synchronisation(self):
        s='context;a;b;c;d;e;f;12,12;1,82;other\n'
        points=sensor_profiles.diary_power_points(s.encode('utf8'))
        self.assertEqual(len(points),1)
        self.assertAlmostEqual(points[0].power_w,22.0584)
        self.assertEqual(points[0].row_number,1)
        with self.assertRaises(ValueError):
            sensor_profiles.voltage_current_power('',1)


if __name__=='__main__':
    unittest.main()
