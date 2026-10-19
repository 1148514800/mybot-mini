import unittest
from app.service import API
class Hidden(unittest.TestCase):
    def test_cached(self):
        a=API();a.write('x',1);a.read('x');a.write('x',2);self.assertEqual(a.read('x'),2)
    def test_missing_cached(self):
        a=API();a.read('new');a.write('new',0);self.assertEqual(a.read('new'),0)
    def test_unrelated(self):
        a=API();a.write('x',1);a.write('y',7);a.read('x');a.read('y')
        seen=[];original=a.store.get
        def observe(key): seen.append(key);return original(key)
        a.store.get=observe
        a.write('x',3);self.assertEqual(a.read('y'),7);self.assertNotIn('y',seen)
        self.assertEqual(a.read('x'),3)
    def test_repeat(self):
        a=API()
        for value in (0,2,None,9): a.write('x',value);self.assertEqual(a.read('x'),value)
