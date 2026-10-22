import unittest
from app.buckets import bucket
class Public(unittest.TestCase):
    def test_between(self): self.assertEqual(bucket(3, [0, 10]), 1)
    def test_empty(self): self.assertEqual(bucket(9, []), 0)
