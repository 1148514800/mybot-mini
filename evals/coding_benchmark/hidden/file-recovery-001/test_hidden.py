import unittest
import tempfile
from pathlib import Path
from app.service import save_document
class Hidden(unittest.TestCase):
    def test_type_preserves(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';p.write_bytes(b'old')
            with self.assertRaises(TypeError): save_document(p,None)
            self.assertEqual(p.read_bytes(),b'old')
    def test_encoding_preserves(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';p.write_bytes(b'old')
            with self.assertRaises(UnicodeEncodeError): save_document(p,'\ud800')
            self.assertEqual(p.read_bytes(),b'old')
    def test_replace(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';p.write_text('old');save_document(p,'新');self.assertEqual(p.read_text(),'新')
    def test_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';save_document(p,'new');self.assertEqual([x.name for x in Path(d).iterdir()],['data'])
