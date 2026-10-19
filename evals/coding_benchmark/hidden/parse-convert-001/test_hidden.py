import unittest
from app.service import load
class Hidden(unittest.TestCase):
    def test_signed(self): self.assertEqual(load(['a:-2','b:+3','c:0']),{'a':-2,'b':3,'c':0})
    def test_colon(self): self.assertEqual(load(['url:a:b:c']),{'url':'a:b:c'})
    def test_spaces_duplicates(self): self.assertEqual(load([' a : 2 ','a:3']),{'a':3})
    def test_invalid(self):
        for value in (' :x','missing'):
            with self.assertRaises(ValueError): load([value])
