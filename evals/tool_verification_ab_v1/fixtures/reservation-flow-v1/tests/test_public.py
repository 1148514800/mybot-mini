import unittest
from app.service import reserve
class Public(unittest.TestCase):
    def test_one(self): self.assertEqual(reserve({'a':5}, [('a',2)]), {'a':3})
    def test_empty(self): self.assertEqual(reserve({'a':0}, []), {'a':0})
