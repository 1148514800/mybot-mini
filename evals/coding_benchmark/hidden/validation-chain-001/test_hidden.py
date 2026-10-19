import unittest
from app.service import register
class Hidden(unittest.TestCase):
    def test_normalize(self): self.assertEqual(register(' A@Example.Test '),{'email':'a@example.test'})
    def test_double(self):
        with self.assertRaises(ValueError): register('a@@example.test')
    def test_domain(self):
        for value in ('a@','a@local','@example.test'):
            with self.assertRaises(ValueError): register(value)
    def test_inner_space(self):
        with self.assertRaises(ValueError): register('a b@example.test')
