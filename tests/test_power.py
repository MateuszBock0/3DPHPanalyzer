import unittest
from power_model import PowerStage, validate, calculate

class TestPower(unittest.TestCase):
    def test_valid_schedule(self):
        self.assertEqual(validate([PowerStage(0,2,5),PowerStage(2,3,0)])[0].q_w, 5)
    def test_overlapping_intervals_fail(self):
        with self.assertRaises(ValueError): validate([PowerStage(0,3,5),PowerStage(2,4,7)])
    def test_unknown_power_is_not_zero(self):
        out = calculate([10,20,30,40], [8,8,8,8], [PowerStage(0,0.5,4)])
        self.assertEqual(out['r'][0], 2)
        self.assertIsNone(out['q'][3])
        self.assertIsNone(out['r'][3])
    def test_zero_power_has_no_resistance(self):
        out = calculate([0,30,60], [10,10,10], [PowerStage(0,2,0)])
        self.assertTrue(all(v is None for v in out['r']))
    def test_reference_needs_constant_power(self):
        out = calculate(list(range(10)), [10.]*10,
                        [PowerStage(0,5/60,10),PowerStage(5/60,2,20)], (0,9/60))
        self.assertIsNotNone(out['reference_error'])
    def test_reference_at_same_power_only(self):
        out = calculate(list(range(10)), [10.]*10,
                        [PowerStage(0,5/60,10),PowerStage(5/60,2,20)], (0,4/60))
        self.assertAlmostEqual(out['r_ref'], 1.)
        self.assertEqual(out['relative'][:5], [1.]*5)
        self.assertTrue(all(x is None for x in out['relative'][5:]))

if __name__ == '__main__': unittest.main()
