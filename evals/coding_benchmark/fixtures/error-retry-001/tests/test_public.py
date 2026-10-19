import unittest
from app.client import execute
class Public(unittest.TestCase):
    def test_success(self): self.assertEqual(execute(lambda:3,1),3)
    def test_value(self): self.assertIsNone(execute(lambda:None,2))
