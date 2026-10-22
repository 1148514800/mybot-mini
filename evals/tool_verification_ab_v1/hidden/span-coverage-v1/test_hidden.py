import unittest
from app.spans import merge_spans
from app.service import coverage
class Hidden(unittest.TestCase):
    def test_overlap(self): self.assertEqual(coverage([(0,5),(2,8),(3,4)]),8)
    def test_unsorted_touch(self): self.assertEqual(merge_spans([(5,8),(0,2),(2,5)]),[(0,8)])
    def test_negative_empty(self):
        self.assertEqual(merge_spans([(-4,0),(-2,2),(9,9)]),[(-4,2)]);self.assertEqual(coverage([(1,1)]),0)
    def test_invalid(self):
        for x in (None, 'x', [(3,2)], [(True,3)], [(0,2.0)], [(1,)], [None]):
            with self.assertRaises(ValueError): coverage(x)
    def test_type_and_mutation(self):
        x=[[3,5],[0,4]];self.assertEqual(merge_spans(x),[(0,5)]);self.assertEqual(x,[[3,5],[0,4]])
    def test_tuple(self): self.assertEqual(coverage(((-3,-1),(-1,2))),5)
