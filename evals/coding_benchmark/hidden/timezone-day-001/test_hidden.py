import unittest
from app.report import utc_day
class Hidden(unittest.TestCase):
    def test_previous_year(self): self.assertEqual(utc_day('2024-01-01T00:30:00+02:00'),'2023-12-31')
    def test_next_day(self): self.assertEqual(utc_day('2024-02-01T23:30:00-02:00'),'2024-02-02')
    def test_minutes(self): self.assertEqual(utc_day('2024-05-01T00:10:00+05:30'),'2024-04-30')
    def test_leap(self): self.assertEqual(utc_day('2024-03-01T00:00:00+01:00'),'2024-02-29')
