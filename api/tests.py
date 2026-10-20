from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    ClassRepresentative,
    College,
    Notification,
    Program,
    SessionReminderPreference,
    Student,
    TimetableSlot,
    University,
)
from api.timetable_ops import send_due_reminders

User = get_user_model()


class TimetablePrivacyTest(TestCase):
    def setUp(self):
        university = University.objects.create(name="UDSM", country="Tanzania")
        college = College.objects.create(name="CoICT", university=university)
        program = Program.objects.create(name="BSc CS", college=college, duration=3)
        self.owner = User.objects.create_user(email="owner@test.com", username="owner", display_name="Owner")
        self.other = User.objects.create_user(email="other@test.com", username="other", display_name="Other")
        self.staff = User.objects.create_user(
            email="staff@test.com", username="staff", display_name="Staff", is_staff=True
        )
        self.owner_student = Student.objects.create(
            user=self.owner, university=university, college=college, program=program, year=1, semester=1
        )
        Student.objects.create(
            user=self.other, university=university, college=college, program=program, year=1, semester=1
        )
        TimetableSlot.objects.create(
            student=self.owner_student,
            course_code="CS101",
            course_name="Intro",
            time_slot="0800-1000",
            day_of_week="monday",
            semester=1,
            academic_year="2024",
        )
        self.client = APIClient()

    def test_student_cannot_read_another_timetable(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(
            "/api/timetable-slots/",
            {"student": str(self.owner_student.id), "semester": 1, "academic_year": "2024"},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_reads_own_timetable(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/api/timetable-slots/", {"semester": 1, "academic_year": "2024"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["course_code"], "CS101")

    def test_staff_can_read_a_student_timetable(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            "/api/timetable-slots/",
            {"student": str(self.owner_student.id), "semester": 1, "academic_year": "2024"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


def _academic_graph(name):
    university = University.objects.create(name=name, country="Tanzania")
    college = College.objects.create(name=f"{name} college", university=university)
    program = Program.objects.create(name=f"{name} programme", college=college, duration=3)
    return university, college, program


def _student(email, program, college, university, year=1):
    user = User.objects.create_user(email=email, username=email.split("@")[0], display_name=email)
    student = Student.objects.create(
        user=user, university=university, college=college, program=program, year=year, semester=1
    )
    return user, student


class TimetableAnnouncementTest(TestCase):
    def setUp(self):
        self.university, self.college, self.program = _academic_graph("UDSM")
        other_university, other_college, other_program = _academic_graph("UDOM")
        self.cr_user, _ = _student("cr@test.com", self.program, self.college, self.university)
        self.member_user, self.member = _student("member@test.com", self.program, self.college, self.university)
        self.outsider_user, self.outsider = _student(
            "out@test.com", other_program, other_college, other_university
        )
        ClassRepresentative.objects.create(user=self.cr_user, program=self.program, is_active=True)
        self.slot = TimetableSlot.objects.create(
            student=self.member, course_code="CS101", course_name="Intro",
            time_slot="0800-1000", day_of_week="monday", semester=1, academic_year="1",
        )
        self.other_slot = TimetableSlot.objects.create(
            student=self.outsider, course_code="CS101", course_name="Intro",
            time_slot="0800-1000", day_of_week="monday", semester=1, academic_year="1",
        )
        self.client = APIClient()

    def _announce(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post("/api/timetable/announcements/", {
            "course_code": "CS101",
            "day_of_week": "monday",
            "time_slot": "0800-1000",
            "semester": 1,
            "academic_year": "1",
            "change_type": "postponed",
            "message": "Moved to Thursday",
            "program": str(self.program.id),
        }, format="json")

    def test_only_class_rep_can_announce_and_only_matching_students_change(self):
        denied = self._announce(self.member_user)
        self.assertEqual(denied.status_code, 403)
        created = self._announce(self.cr_user)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["affected_count"], 1)
        self.slot.refresh_from_db()
        self.other_slot.refresh_from_db()
        self.assertEqual(self.slot.status, "postponed")
        self.assertEqual(self.other_slot.status, "scheduled")
        self.assertTrue(Notification.objects.filter(user=self.member_user, title__icontains="CS101").exists())
        self.assertFalse(Notification.objects.filter(user=self.outsider_user).exists())
        duplicate = self._announce(self.cr_user)
        self.assertEqual(duplicate.status_code, 409)


class SessionReminderTest(TestCase):
    def test_cancelled_session_is_not_reminded_and_delivery_is_once(self):
        university, college, program = _academic_graph("Reminder U")
        user, student = _student("remind@test.com", program, college, university)
        SessionReminderPreference.objects.create(user=user, enabled=True, minutes_before=30)
        moment = timezone.make_aware(datetime(2026, 10, 19, 9, 0))
        TimetableSlot.objects.create(
            student=student, course_code="MT100", time_slot="0920-1020",
            day_of_week="monday", semester=1, academic_year="1", status="scheduled", venue="A4",
        )
        TimetableSlot.objects.create(
            student=student, course_code="MT200", time_slot="0920-1020",
            day_of_week="monday", semester=1, academic_year="1", status="cancelled", venue="B1",
        )
        self.assertEqual(send_due_reminders(moment), 1)
        self.assertEqual(send_due_reminders(moment), 0)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)
        self.assertIn("MT100", Notification.objects.get(user=user).title)


class ArticleCategoryTest(TestCase):
    def test_revelational_comes_from_model_choices(self):
        user = User.objects.create_user(email="reader@test.com", username="reader", display_name="Reader")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/articles/categories/")
        self.assertEqual(response.status_code, 200)
        slugs = [item["slug"] for item in response.data]
        self.assertIn("revelational", slugs)
        self.assertIn("campus_life", slugs)


class TimetableExportTest(TestCase):
    def test_export_png_requires_auth_and_returns_an_image(self):
        university, college, program = _academic_graph("Export U")
        user, student = _student("export@test.com", program, college, university)
        TimetableSlot.objects.create(
            student=student, course_code="CS101", time_slot="0800-1000",
            day_of_week="monday", semester=1, academic_year="1", venue="Hall A",
        )
        client = APIClient()
        self.assertEqual(client.get("/api/timetable/export/").status_code, 401)
        client.force_authenticate(user=user)
        response = client.get("/api/timetable/export/", {"file": "png"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
