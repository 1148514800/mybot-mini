import unittest
import json
from app.records import Record,to_record
class Hidden(unittest.TestCase):
    def test_false(self): self.assertIs(to_record(Record('x'))['active'],False)
    def test_zero(self): self.assertEqual(to_record(Record('x'))['count'],0)
    def test_empty(self): self.assertEqual(to_record(Record('',tag=''))['tag'],'')
    def test_roundtrip(self): self.assertEqual(json.loads(json.dumps(to_record(Record('x')))),{'name':'x','active':False,'count':0})
