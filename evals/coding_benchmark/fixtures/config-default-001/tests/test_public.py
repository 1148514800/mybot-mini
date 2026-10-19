import unittest
from app.options import enabled
class Public(unittest.TestCase):
    def test_true(self): self.assertTrue(enabled({'x':True},'x'))
    def test_default(self): self.assertTrue(enabled({},'x',True))
