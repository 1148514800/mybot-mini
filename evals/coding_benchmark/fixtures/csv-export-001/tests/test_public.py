import unittest
from app.export import export
class Public(unittest.TestCase):
    def test_basic(self): self.assertEqual(export([['a','b']]),'a,b\n')
    def test_empty(self): self.assertEqual(export([]),'')
