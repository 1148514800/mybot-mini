import unittest
from app.service import load
class Public(unittest.TestCase):
    def test_text(self): self.assertEqual(load(['name:alice']),{'name':'alice'})
    def test_empty(self): self.assertEqual(load([]),{})
