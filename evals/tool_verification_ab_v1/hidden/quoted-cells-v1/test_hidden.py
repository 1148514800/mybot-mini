import unittest
from app.cells import parse_row
class Hidden(unittest.TestCase):
    def test_quoted(self): self.assertEqual(parse_row('"red;blue";green'), ['red;blue','green'])
    def test_escape(self): self.assertEqual(parse_row('"a""b";""'), ['a"b',''])
    def test_empty_fields(self): self.assertEqual(parse_row(';x;;'),['','x','',''])
    def test_spaces(self): self.assertEqual(parse_row(' a ; b '),[' a ',' b '])
    def test_invalid(self):
        for x in ('"open', '"closed"junk', 'a\nb', '"a\rb"'):
            with self.assertRaises(ValueError): parse_row(x)
    def test_types(self):
        for x in (None, False, 0, [], b'a;b'):
            with self.assertRaises(ValueError): parse_row(x)
