import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from api.models import College, Program, Student, University
from api.onboarding import assign_firebase_picture

User = get_user_model()


class OnboardingSocialProofTest(TestCase):
    def setUp(self):
        self.university = University.objects.create(name="UDSM", country="Tanzania")
        self.college = College.objects.create(name="CoICT", university=self.university)
        self.other_college = College.objects.create(name="CoET", university=self.university)
        self.program = Program.objects.create(name="BSc CS", college=self.college, duration=3)
        self.other_program = Program.objects.create(name="BSc EE", college=self.other_college, duration=4)
        self.me = User.objects.create_user(email="me@test.com", username="me", display_name="Me")
        Student.objects.create(
            user=self.me, university=self.university, college=self.college, program=self.program, year=2, semester=1
        )
        self.classmate = User.objects.create_user(
            email="class@test.com", username="class", display_name="Amina", profile_picture="https://example.com/a.png"
        )
        Student.objects.create(
            user=self.classmate, university=self.university, college=self.college, program=self.program, year=2, semester=1
        )
        hidden = User.objects.create_user(
            email="hidden@test.com", username="hidden", display_name="Hidden", public_profile=False
        )
        Student.objects.create(
            user=hidden, university=self.university, college=self.college, program=self.program, year=2, semester=1
        )
        self.client = APIClient()
        self.client.force_authenticate(self.me)

    def test_same_programme_year_excludes_self_and_private_profiles(self):
        response = self.client.get("/api/onboarding/social-proof/")
        self.assertEqual(response.status_code, 200)
        names = [person["display_name"] for person in response.data["people"]]
        self.assertEqual(names, ["Amina"])
        self.assertEqual(response.data["match"], "programme_year")
        self.assertIsNotNone(response.data["student_number"])
        self.assertGreaterEqual(response.data["platform_count"], 1)

    def test_falls_back_to_programme_then_college(self):
        self.classmate.student_profile.year = 4
        self.classmate.student_profile.save(update_fields=["year"])
        response = self.client.get("/api/onboarding/social-proof/")
        self.assertEqual(response.data["match"], "programme")

        self.classmate.student_profile.program = self.other_program
        self.classmate.student_profile.college = self.other_college
        self.classmate.student_profile.save()
        programme_only = User.objects.create_user(email="col@test.com", username="col", display_name="Juma")
        Student.objects.create(
            user=programme_only,
            university=self.university,
            college=self.college,
            program=self.other_program,
            year=1,
            semester=1,
        )
        # Juma is in another programme but the same university. College differs, so no match.
        programme_only.student_profile.college = self.college
        programme_only.student_profile.program = Program.objects.create(
            name="BSc IS", college=self.college, duration=3
        )
        programme_only.student_profile.save()
        response = self.client.get("/api/onboarding/social-proof/")
        self.assertEqual(response.data["match"], "college")
        self.assertEqual(response.data["people"][0]["display_name"], "Juma")

    def test_skip_sets_a_cooldown_and_existing_style_legacy_hides_the_card(self):
        skipped = self.client.patch("/api/onboarding/", {"interests_status": "skipped"}, format="json")
        self.assertEqual(skipped.status_code, 200)
        self.assertEqual(skipped.data["state"]["interests_status"], "skipped")
        self.assertFalse(skipped.data["show_card"])

        self.me.onboarding_state = {"social_seen": True, "interests_status": "legacy"}
        self.me.save(update_fields=["onboarding_state"])
        progress = self.client.get("/api/onboarding/")
        self.assertFalse(progress.data["show_card"])
        self.assertEqual(progress.data["state"]["social_seen"], True)


def tiny_png(name="face.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 80, 160)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class ProfilePhotoAndPublicCountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="photo@test.com", username="photo", display_name="Photo")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_public_count_is_anonymous_and_counts_active_users_only(self):
        User.objects.create_user(email="off@test.com", username="off", display_name="Off", is_active=False)
        response = APIClient().get("/api/public/user-count/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"user_count": User.objects.filter(is_active=True).count()})

    def test_upload_saves_a_photo_and_google_cannot_replace_it(self):
        rejected = self.client.post(
            "/api/user/profile-picture/",
            {"image": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(rejected.status_code, 400)

        uploaded = self.client.post(
            "/api/user/profile-picture/",
            {"image": tiny_png()},
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 200)
        self.assertTrue(str(uploaded.data["profile_picture"]).startswith("http"))
        self.user.refresh_from_db()
        saved = self.user.profile_picture
        self.assertEqual(self.user.onboarding_state["photo_status"], "saved")
        self.assertFalse(assign_firebase_picture(self.user, "https://google.example/other.png"))
        self.assertEqual(self.user.profile_picture, saved)

        removed = self.client.delete("/api/user/profile-picture/")
        self.assertEqual(removed.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture, "https://google.example/other.png")
        self.assertEqual(self.user.onboarding_state["photo_status"], "skipped")

    def test_skip_waits_five_days_and_an_old_account_is_prompted(self):
        fresh = User.objects.create_user(email="new@test.com", username="new", display_name="New")
        fresh.onboarding_state = {"social_seen": True, "interests_status": "legacy"}
        fresh.date_joined = timezone.now() - timedelta(days=1)
        fresh.save(update_fields=["onboarding_state", "date_joined"])
        client = APIClient()
        client.force_authenticate(fresh)
        recent = client.get("/api/onboarding/")
        self.assertFalse(recent.data["show_photo_prompt"])

        fresh.date_joined = timezone.now() - timedelta(days=6)
        fresh.save(update_fields=["date_joined"])
        due = client.get("/api/onboarding/")
        self.assertTrue(due.data["show_photo_prompt"])

        skipped = self.client.patch("/api/onboarding/", {"photo_status": "skipped"}, format="json")
        self.assertEqual(skipped.data["state"]["photo_status"], "skipped")
        self.assertFalse(skipped.data["show_photo_prompt"])

    def test_empty_picture_can_be_filled_from_google(self):
        self.assertTrue(assign_firebase_picture(self.user, "https://google.example/a.png"))
        self.assertEqual(self.user.profile_picture, "https://google.example/a.png")

    def test_google_photo_is_kept_current_until_the_user_replaces_it(self):
        self.assertTrue(assign_firebase_picture(self.user, "https://google.example/a.png"))
        self.user.save(update_fields=["profile_picture"])
        self.assertTrue(assign_firebase_picture(self.user, "https://google.example/b.png"))
        self.user.save(update_fields=["profile_picture"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture, "https://google.example/b.png")

        uploaded = self.client.post("/api/user/profile-picture/", {"image": tiny_png("mine.png")}, format="multipart")
        self.assertEqual(uploaded.status_code, 200)
        self.user.refresh_from_db()
        custom = self.user.profile_picture
        self.assertFalse(assign_firebase_picture(self.user, "https://google.example/c.png"))
        self.assertEqual(self.user.profile_picture, custom)

        removed = self.client.delete("/api/user/profile-picture/")
        self.assertEqual(removed.data["profile_picture"], "https://google.example/c.png")
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture, "https://google.example/c.png")
        self.assertNotEqual(self.user.onboarding_state["photo_status"], "saved")
