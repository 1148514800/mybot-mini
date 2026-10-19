import unittest
from app.cache import Cache
class Public(unittest.TestCase):
    def test_fresh(self):
        c=Cache();c.put('a',3,10,5);self.assertEqual(c.get('a',11),3)
    def test_missing(self): self.assertIsNone(Cache().get('x',0))
