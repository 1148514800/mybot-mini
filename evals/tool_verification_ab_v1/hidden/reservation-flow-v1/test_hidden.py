import unittest
from app.service import reserve
from app.validation import validate_stock, normalize_orders
class Hidden(unittest.TestCase):
    def test_normalization(self): self.assertEqual(reserve({'a':5}, [(' a ',2),('a',1)]), {'a':2})
    def test_overdraw(self):
        for orders in ([('a',6)],[('a',3),('a',3)],[('x',1)]):
            with self.assertRaises(ValueError): reserve({'a':5},orders)
    def test_quantity(self):
        for q in (True, False, 0, -1, '2', 2.0, None):
            with self.assertRaises(ValueError): reserve({'a':5},[('a',q)])
    def test_stock(self):
        for stock in (None, [], {'a':True},{'a':-1},{'':2},{' a':2},{3:2}):
            with self.assertRaises(ValueError): validate_stock(stock)
    def test_orders(self):
        for orders in (None, {'a':2}, [None], [('a',)], [(' ',1)], [(2,1)]):
            with self.assertRaises(ValueError): normalize_orders(orders)
    def test_immutable(self):
        stock={'a':5};orders=[[' a ',2]]
        result=reserve(stock,orders);self.assertEqual(result,{'a':3});self.assertIsNot(result,stock)
        self.assertEqual(stock,{'a':5});self.assertEqual(orders,[[' a ',2]])
        with self.assertRaises(ValueError): reserve(stock,[('a',10)])
        self.assertEqual(stock,{'a':5})
