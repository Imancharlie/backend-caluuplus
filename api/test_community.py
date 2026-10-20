import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from api.community import notify_due_community_events
from api.models import CommunityResponse, CommunityStory, Notification

User = get_user_model()


def tiny_png(name="campus.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), (0, 191, 255)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class CommunityStoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.author = User.objects.create_user(
            email="author@test.com", username="author", display_name="Amina"
        )
        self.reader = User.objects.create_user(
            email="reader@test.com", username="reader", display_name="Baraka"
        )
        self.author_client = APIClient()
        self.reader_client = APIClient()
        self.anon = APIClient()
        self.author_client.force_authenticate(self.author)
        self.reader_client.force_authenticate(self.reader)

    def test_question_persists_and_can_be_discussed(self):
        created = self.author_client.post(
            "/api/community/stories/",
            {"kind": "question", "title": "What do you wish you knew earlier?", "body": "Share one lesson."},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        code = created.data["share_code"]
        story = CommunityStory.objects.get(share_code=code)
        self.assertNotEqual(code, str(story.id))
        self.assertNotIn(str(story.id), created.data["share_url"])

        reply = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "Start assignments before the week gets loud."},
            format="json",
        )
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertTrue(
            Notification.objects.filter(user=self.author, link=f"/stories/{code}").exists()
        )

        story.published_at = timezone.now() - timedelta(hours=48)
        story.save(update_fields=["published_at"])
        listed = self.reader_client.get("/api/community/stories/")
        codes = [item["share_code"] for item in listed.data["results"]]
        self.assertIn(code, codes)
        discussion = self.reader_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual(discussion.data["count"], 1)
        self.assertTrue(CommunityResponse.objects.filter(story=story).exists())
        self.assertTrue(User.objects.filter(pk=self.author.pk).exists())

    def test_other_user_cannot_edit_or_delete(self):
        created = self.author_client.post(
            "/api/community/stories/",
            {"kind": "question", "title": "How do you revise?", "body": ""},
            format="json",
        )
        code = created.data["share_code"]
        denied = self.reader_client.patch(
            f"/api/community/stories/{code}/",
            {"title": "Changed"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.anon.get("/api/community/stories/").status_code, 401)

    def test_photo_expires_from_the_active_row_without_deleting_people(self):
        created = self.author_client.post(
            "/api/community/stories/",
            {"kind": "photo", "body": "Library steps after rain", "campus_name": "Mlimani", "image": tiny_png()},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.content)
        code = created.data["share_code"]
        self.assertTrue(created.data["is_active_story"])
        self.assertIsNotNone(created.data["expires_at"])

        comment = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "That light is beautiful."},
            format="json",
        )
        self.assertEqual(comment.status_code, 201, comment.content)

        story = CommunityStory.objects.get(share_code=code)
        story.expires_at = timezone.now() - timedelta(minutes=5)
        story.save(update_fields=["expires_at"])

        listed = self.reader_client.get("/api/community/stories/")
        codes = [item["share_code"] for item in listed.data["results"]]
        self.assertNotIn(code, codes)
        detail = self.reader_client.get(f"/api/community/stories/{code}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["is_active_story"])
        self.assertEqual(CommunityResponse.objects.filter(story=story).count(), 1)
        self.assertTrue(User.objects.filter(pk=self.author.pk).exists())

    def test_quiz_hides_answers_until_reveal_and_blocks_a_second_submission(self):
        reveal_at = timezone.now() + timedelta(days=2)
        ends_at = timezone.now() + timedelta(days=1)
        created = self.author_client.post(
            "/api/community/stories/",
            {
                "kind": "competition",
                "title": "Name the process plants use",
                "body": "One word is enough.",
                "competition_format": "quiz",
                "correct_answer": "photosynthesis",
                "explanation": "Plants convert light into energy.",
                "ends_at": ends_at.isoformat(),
                "reveal_at": reveal_at.isoformat(),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        code = created.data["share_code"]
        self.assertEqual(created.data["competition"]["correct_answer"], "photosynthesis")

        first = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "water", "is_submission": True},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertNotIn("score", first.data)

        duplicate = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "photosynthesis", "is_submission": True},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)

        hidden = self.reader_client.get(f"/api/community/stories/{code}/")
        self.assertNotIn("correct_answer", hidden.data["competition"])
        self.assertFalse(hidden.data["competition"]["answers_revealed"])
        visible_to_author = self.author_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual(visible_to_author.data["count"], 1)
        visible_to_reader = self.reader_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual(visible_to_reader.data["count"], 1)
        self.assertEqual(visible_to_reader.data["results"][0]["body"], "water")

        story = CommunityStory.objects.get(share_code=code)
        story.reveal_at = timezone.now() - timedelta(minutes=1)
        story.save(update_fields=["reveal_at"])
        revealed = self.reader_client.get(f"/api/community/stories/{code}/")
        self.assertTrue(revealed.data["competition"]["answers_revealed"])
        self.assertEqual(revealed.data["competition"]["correct_answer"], "photosynthesis")
        scored = self.reader_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual(scored.data["results"][0]["score"], 0)

        notify_due_community_events(force=True)
        self.assertTrue(
            Notification.objects.filter(user=self.reader, title="Challenge results are available").exists()
        )
        story.refresh_from_db()
        self.assertTrue(story.results_notified)
        before = Notification.objects.filter(title="Challenge results are available").count()
        notify_due_community_events(force=True)
        after = Notification.objects.filter(title="Challenge results are available").count()
        self.assertEqual(before, after)

    def test_closed_competition_keeps_submissions(self):
        ends_at = timezone.now() + timedelta(hours=2)
        created = self.author_client.post(
            "/api/community/stories/",
            {
                "kind": "competition",
                "title": "Best study spot",
                "body": "Name one place.",
                "competition_format": "deadline",
                "ends_at": ends_at.isoformat(),
            },
            format="json",
        )
        code = created.data["share_code"]
        submitted = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "The quiet floor of the library"},
            format="json",
        )
        self.assertEqual(submitted.status_code, 201, submitted.content)
        story = CommunityStory.objects.get(share_code=code)
        story.ends_at = timezone.now() - timedelta(minutes=1)
        story.save(update_fields=["ends_at"])
        late = self.author_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "Too late", "is_submission": True},
            format="json",
        )
        self.assertEqual(late.status_code, 400)
        self.assertTrue(CommunityResponse.objects.filter(story=story, user=self.reader).exists())
        listed = self.reader_client.get("/api/community/stories/")
        self.assertIn(code, [item["share_code"] for item in listed.data["results"]])
        detail = self.reader_client.get(f"/api/community/stories/{code}/")
        self.assertTrue(detail.data["competition"]["closed"])
        self.assertTrue(detail.data["competition"]["answers_revealed"])

    def test_photo_can_post_without_a_caption_and_stays_two_days(self):
        created = self.author_client.post(
            "/api/community/stories/",
            {"kind": "photo", "image": tiny_png("bare.png")},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.content)
        code = created.data["share_code"]
        story = CommunityStory.objects.get(share_code=code)
        self.assertTrue(story.image)
        self.assertIsNotNone(story.purge_at)
        self.assertGreater(story.purge_at, story.expires_at)
        self.assertLessEqual(story.expires_at - story.published_at, timedelta(hours=24, minutes=1))
        self.assertGreaterEqual(story.purge_at - story.published_at, timedelta(hours=47))

        story.expires_at = timezone.now() - timedelta(minutes=1)
        story.save(update_fields=["expires_at"])
        listed = self.reader_client.get("/api/community/stories/")
        self.assertNotIn(code, [item["share_code"] for item in listed.data["results"]])
        self.assertTrue(CommunityStory.objects.filter(share_code=code).exists())

        story.purge_at = timezone.now() - timedelta(minutes=1)
        story.save(update_fields=["purge_at"])
        listed_again = self.reader_client.get("/api/community/stories/")
        self.assertNotIn(code, [item["share_code"] for item in listed_again.data["results"]])
        self.assertFalse(CommunityStory.objects.filter(share_code=code).exists())

    def test_learned_card_limits_text_and_hides_other_comments(self):
        too_long = self.author_client.post(
            "/api/community/stories/",
            {"kind": "learned", "title": "x" * 401, "comments_hidden": True},
            format="json",
        )
        self.assertEqual(too_long.status_code, 400)

        created = self.author_client.post(
            "/api/community/stories/",
            {"kind": "learned", "title": "Integrals are just accumulated change.", "comments_hidden": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(created.data["comments_hidden"])
        self.assertLessEqual(len(created.data["title"]), 400)

        longer = self.author_client.post(
            "/api/community/stories/",
            {"kind": "learned", "title": "y" * 200},
            format="json",
        )
        self.assertEqual(longer.status_code, 201, longer.content)
        self.assertEqual(len(longer.data["title"]), 200)
        code = created.data["share_code"]

        mine = self.reader_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "That finally clicked."},
            format="json",
        )
        self.assertEqual(mine.status_code, 201, mine.content)
        reply = self.author_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "Glad it did.", "parent_id": mine.data["id"]},
            format="json",
        )
        self.assertEqual(reply.status_code, 201, reply.content)

        other = User.objects.create_user(email="other@test.com", username="other", display_name="Neema")
        other_client = APIClient()
        other_client.force_authenticate(other)
        secret = other_client.post(
            f"/api/community/stories/{code}/responses/",
            {"body": "I already knew this."},
            format="json",
        )
        self.assertEqual(secret.status_code, 201, secret.content)

        reader_view = self.reader_client.get(f"/api/community/stories/{code}/responses/")
        reader_bodies = [item["body"] for item in reader_view.data["results"]]
        self.assertEqual(reader_bodies, ["That finally clicked.", "Glad it did."])
        other_view = other_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual([item["body"] for item in other_view.data["results"]], ["I already knew this."])
        author_view = self.author_client.get(f"/api/community/stories/{code}/responses/")
        self.assertEqual(author_view.data["count"], 3)

        listed = self.reader_client.get("/api/community/stories/")
        self.assertIn(code, [item["share_code"] for item in listed.data["results"]])
