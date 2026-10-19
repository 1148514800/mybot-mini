import unittest
from app.cli import parse
from app.configuration import merge
class Public(unittest.TestCase):
    def test_defaults(self): self.assertEqual(merge({},parse([])),{'retries':3,'verbose':False})
    def test_override(self): self.assertEqual(merge({'retries':8},parse(['--retries','4']))['retries'],4)
