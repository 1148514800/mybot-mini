import unittest
from app.service import API
class Public(unittest.TestCase):
    def test_missing(self): self.assertIsNone(API().read('missing'))
    def test_first_write(self):
        api=API();api.write('a',1);self.assertEqual(api.read('a'),1)
