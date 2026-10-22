import unittest
from app.service import coverage
class Public(unittest.TestCase):
    def test_disjoint(self): self.assertEqual(coverage([(1,3),(6,9)]),5)
    def test_empty(self): self.assertEqual(coverage([]),0)
