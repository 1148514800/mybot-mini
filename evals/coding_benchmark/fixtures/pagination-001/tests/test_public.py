import unittest
from app.paging import paginate
class Public(unittest.TestCase):
    def test_empty(self): self.assertEqual(paginate([],1,3),[])
    def test_single(self): self.assertEqual(paginate([1],1,3),[1])
