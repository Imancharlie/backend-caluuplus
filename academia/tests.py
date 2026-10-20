from datetime import date

from django.test import TestCase

from academia.models import GlobalSemesterCalendar


class GlobalSemesterCalendarTests(TestCase):
    def test_one_window_covers_every_university(self):
        GlobalSemesterCalendar.objects.create(
            semester_1_start=date(2026, 10, 1),
            semester_1_end=date(2027, 2, 1),
            semester_2_start=date(2027, 3, 1),
            semester_2_end=date(2027, 7, 1),
        )
        row = GlobalSemesterCalendar.objects.get(pk=1)
        self.assertEqual(row.window_on(date(2026, 11, 2)), (1, date(2026, 10, 1)))
        self.assertEqual(row.window_on(date(2027, 4, 10)), (2, date(2027, 3, 1)))
        self.assertEqual(row.window_on(date(2027, 2, 15)), (None, None))
        self.assertEqual(row.window_on(date(2026, 9, 1)), (None, None))
