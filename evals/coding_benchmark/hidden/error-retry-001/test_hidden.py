import unittest
from app.client import execute
class Hidden(unittest.TestCase):
    def test_zero(self): self.assertEqual(execute(lambda:7,0),7)
    def test_count(self):
        seen=[]
        def fail(): seen.append(1);raise OSError('temporary')
        with self.assertRaises(OSError): execute(fail,2)
        self.assertEqual(len(seen),3)
    def test_non_retry(self):
        seen=[];error=ValueError('permanent')
        def fail(): seen.append(1);raise error
        with self.assertRaises(ValueError) as got: execute(fail,4)
        self.assertIs(got.exception,error);self.assertEqual(len(seen),1)
    def test_last(self):
        errors=[OSError('a'),OSError('b')];seen=[]
        def fail(): error=errors[len(seen)];seen.append(1);raise error
        with self.assertRaises(OSError) as got: execute(fail,1)
        self.assertIs(got.exception,errors[-1])
