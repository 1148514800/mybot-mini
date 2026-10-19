import unittest
import csv,io
from app.export import export
class Hidden(unittest.TestCase):
    def check(self,row): self.assertEqual(list(csv.reader(io.StringIO(export([row]),newline=''))),[row])
    def test_comma(self): self.check(['a,b','c'])
    def test_quote(self): self.check(['a"b','c'])
    def test_newline(self):
        for value in ('a\nb','a\rb','a\r\nb'): self.check([value,'c'])
    def test_unicode_empty(self): self.check(['你好','','tail'])
