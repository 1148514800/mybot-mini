import unittest
from app.paging import paginate
class Hidden(unittest.TestCase):
    def test_full(self): self.assertEqual(paginate(list(range(9)),1,3),[0,1,2])
    def test_next(self): self.assertEqual(paginate(list(range(9)),2,3),[3,4,5])
    def test_tail(self): self.assertEqual(paginate([1,2,3,4],2,3),[4])
    def test_invalid(self):
        for p,s in [(0,2),(1,0),(True,2),(1,False),(-1,2)]:
            with self.assertRaises(ValueError): paginate([1],p,s)
