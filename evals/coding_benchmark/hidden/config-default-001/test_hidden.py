import unittest
from app.options import enabled
class Hidden(unittest.TestCase):
    def test_false(self): self.assertIs(enabled({'x':False},'x',True),False)
    def test_missing(self): self.assertIs(enabled({},'x'),False)
    def test_numbers(self):
        for value in (0,1,None):
            with self.assertRaises(ValueError): enabled({'x':value},'x')
    def test_string(self):
        with self.assertRaises(ValueError): enabled({'x':'false'},'x')
