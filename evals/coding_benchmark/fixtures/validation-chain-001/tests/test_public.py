import unittest
from app.service import register
class Public(unittest.TestCase):
    def test_basic(self): self.assertEqual(register('a@example.test'),{'email':'a@example.test'})
    def test_missing(self):
        with self.assertRaises(ValueError): register('invalid')
