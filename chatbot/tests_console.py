"""Tests for the superuser chat console.

Covers the parts that are easy to get wrong: the privilege gate, the sign-in
flow, and that the page hands the browser a working token plus a pre-serialised
history (an unserialisable datetime here would 500 the whole page).
"""

import json
import re

from django.test import TestCase
from django.urls import reverse

from chatbot.models import Conversation, Message
from api.models import User


class ConsoleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="root-admin", email="root@example.com", password="Str0ngPass!23"
        )
        self.plain = User.objects.create_user(
            username="regular", email="user@example.com", password="Str0ngPass!23"
        )

    def test_anonymous_is_redirected_to_login(self):
        res = self.client.get(reverse("chatbot-console"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("chatbot-console-login"), res["Location"])

    def test_non_superuser_is_rejected(self):
        self.client.force_login(self.plain)
        res = self.client.get(reverse("chatbot-console"))
        # Redirects away with an error rather than rendering the console.
        self.assertEqual(res.status_code, 302)

    def test_superuser_sees_the_console(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("chatbot-console"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Mr. Caluu")
        self.assertContains(res, "New Chat")

    def test_login_rejects_bad_password(self):
        res = self.client.post(
            reverse("chatbot-console-login"),
            {"email": "root@example.com", "password": "wrong"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Invalid email or password")

    def test_login_refuses_non_superusers(self):
        res = self.client.post(
            reverse("chatbot-console-login"),
            {"email": "user@example.com", "password": "Str0ngPass!23"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "restricted to superusers")

    def test_login_succeeds_for_superuser(self):
        res = self.client.post(
            reverse("chatbot-console-login"),
            {"email": "root@example.com", "password": "Str0ngPass!23"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("chatbot-console"), res["Location"])

    def test_logout_ends_the_session(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("chatbot-console-logout"))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.get(reverse("chatbot-console")).status_code, 302)

    def test_page_embeds_a_usable_token_and_valid_history_json(self):
        convo = Conversation.objects.create(user=self.admin, title="Fees question")
        Message.objects.create(conversation=convo, role="user", content="hi")
        Message.objects.create(conversation=convo, role="assistant", content="hello")

        self.client.force_login(self.admin)
        res = self.client.get(reverse("chatbot-console"))

        raw = res.content.decode("utf-8")
        # Extract the JSON island between the bootstrap script tags. A regex is
        # used rather than slicing because the closing tag is already excluded
        # from the slice.
        match = re.search(
            r'<script id="bootstrap"[^>]*>(.*?)</script>', raw, re.DOTALL
        )
        self.assertIsNotNone(match, "bootstrap script tag not found in the page")
        payload = json.loads(match.group(1))

        # A token that is empty, or literally the string "None", breaks the page.
        self.assertTrue(payload["token"])
        self.assertNotEqual(payload["token"], "None")

        # datetime objects must have been serialised server-side.
        self.assertIsInstance(payload["histories"], list)
        self.assertEqual(len(payload["histories"]), 1)
        entry = payload["histories"][0]
        self.assertEqual(entry["id"], str(convo.id))
        self.assertEqual(entry["message_count"], 2)

    def test_history_only_contains_the_signed_in_user(self):
        other = User.objects.create_user(
            username="other", email="other@example.com", password="Str0ngPass!23"
        )
        Conversation.objects.create(user=other, title="Someone elses thread")
        mine = Conversation.objects.create(user=self.admin, title="My thread")

        self.client.force_login(self.admin)
        res = self.client.get(reverse("chatbot-console"))
        raw = res.content.decode("utf-8")

        self.assertIn(str(mine.id), raw)
        self.assertNotIn("Someone elses thread", raw)