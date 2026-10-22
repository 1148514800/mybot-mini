import unittest
from app.buckets import bucket
class Hidden(unittest.TestCase):
    def test_equal(self): self.assertEqual(bucket(10, [0, 10, 20]), 2)
    def test_negative(self): self.assertEqual(bucket(-4, (-8, -4, 0)), 2)
    def test_bad_value(self):
        for x in (True, False, None, 1.0, '1'):
            with self.assertRaises(ValueError): bucket(x, [])
    def test_bad_container(self):
        for x in (None, '123', {1,2}, 3):
            with self.assertRaises(ValueError): bucket(1, x)
    def test_bad_elements(self):
        for x in ([False], [1.0], [None], [2,1], [1,1]):
            with self.assertRaises(ValueError): bucket(1, x)
    def test_no_mutation(self):
        x=[-1,0,2]; self.assertEqual(bucket(0,x),2);self.assertEqual(x,[-1,0,2])
