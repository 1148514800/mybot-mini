import unittest
from app.cells import parse_row
class Public(unittest.TestCase):
    def test_plain(self): self.assertEqual(parse_row('a;b'), ['a','b'])
    def test_empty(self): self.assertEqual(parse_row(''), [])
