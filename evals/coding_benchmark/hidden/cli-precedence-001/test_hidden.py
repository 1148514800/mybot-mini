import unittest
from app.cli import parse
from app.configuration import merge
class Hidden(unittest.TestCase):
    def test_zero_cli(self): self.assertEqual(merge({'retries':9},parse(['--retries','0']))['retries'],0)
    def test_config(self): self.assertEqual(merge({'retries':8},parse([]))['retries'],8)
    def test_zero_config(self): self.assertEqual(merge({'retries':0},parse([]))['retries'],0)
    def test_verbose(self):
        self.assertTrue(merge({'verbose':True},parse([]))['verbose'])
        self.assertTrue(merge({'verbose':False},parse(['--verbose']))['verbose'])
