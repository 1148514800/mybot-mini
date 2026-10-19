import unittest
from app.cache import Cache
class Hidden(unittest.TestCase):
    def test_boundary(self):
        c=Cache();c.put('a',4,10,5);self.assertIsNone(c.get('a',15))
    def test_zero(self):
        c=Cache();c.put('a',4,10,0);self.assertIsNone(c.get('a',10))
    def test_before(self):
        c=Cache();c.put('a',4,10,5);self.assertEqual(c.get('a',14.999),4)
    def test_negative(self):
        with self.assertRaises(ValueError): Cache().put('a',4,10,-1)
