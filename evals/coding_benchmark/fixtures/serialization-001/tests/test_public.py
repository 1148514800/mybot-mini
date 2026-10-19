import unittest
from app.records import Record,to_record
class Public(unittest.TestCase):
    def test_name(self): self.assertEqual(to_record(Record('x'))['name'],'x')
    def test_none(self): self.assertNotIn('tag',to_record(Record('x')))
