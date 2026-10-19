import unittest
from app.report import utc_day
class Public(unittest.TestCase):
    def test_naive(self): self.assertEqual(utc_day('2024-01-02T12:00:00'),'2024-01-02')
    def test_z(self): self.assertEqual(utc_day('2024-01-02T12:00:00Z'),'2024-01-02')
