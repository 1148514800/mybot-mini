import unittest
import tempfile
from pathlib import Path
from app.service import save_document
class Public(unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';save_document(p,'hello');self.assertEqual(p.read_text(),'hello')
    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';save_document(p,'');self.assertEqual(p.read_bytes(),b'')
