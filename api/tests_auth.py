"""Tests for Google/Firebase sign-in hardening.

The reported symptom was a login flow that intermittently reported "server
unreachable", dropped the user back out, and on a later successful sign-in mixed
the newly signed-in profile picture with the previous account's data.

Three distinct server-side defects are pinned here:

1.  The route only existed with a trailing slash while production.py sets
    APPEND_SLASH=False, so a client built against the other spelling got a hard
    404 -- indistinguishable from a dead server at the app layer.
2.  Only the "token" payload key was read, so a client sending "id_token" was
    told the token was missing.
3.  Error responses had no machine-readable code, so the app could not tell
    "sign in again" apart from "server is down".

Plus the invariant that matters most for the data-mixing report: two different
Firebase accounts must never resolve to each other's user row.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import resolve

from api.models import User


class RouteAliasTests(TestCase):
    """Both slash spellings must reach the view.

    APPEND_SLASH=False means Django will not paper over a mismatch.
    """

    def test_both_variants_resolve(self):
        for path in ("/api/auth/firebase-login/", "/api/auth/firebase-login"):
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.func.cls.__name__, "FirebaseLoginView")

    def test_refresh_has_a_route(self):
        # @api_view wraps the function, so only assert it resolves to a callable.
        self.assertTrue(callable(resolve("/api/auth/refresh/").func))


class FirebaseLoginContractTests(TestCase):
    URL = "/api/auth/firebase-login/"

    def _post(self, payload):
        return self.client.post(self.URL, payload, content_type="application/json")

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_accepts_token_key(self, verify, _app):
        verify.return_value = {
            "uid": "uid-a", "email": "a@example.com",
            "name": "Alpha One", "picture": "https://img/a.png",
        }
        r = self._post({"token": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["email"], "a@example.com")

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_accepts_id_token_key(self, verify, _app):
        """A client sending 'id_token' must not be told the token is missing."""
        verify.return_value = {
            "uid": "uid-b", "email": "b@example.com", "name": "Beta Two",
        }
        r = self._post({"id_token": "abc"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["user"]["email"], "b@example.com")

    def test_missing_token_is_actionable(self):
        r = self._post({})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "missing_token")

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_expired_token_reports_token_expired(self, verify, _app):
        """An expired Firebase token must not look like a dead server."""
        verify.side_effect = Exception("Firebase ID token has expired.")
        r = self._post({"token": "abc"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "token_expired")

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_invalid_token_reports_invalid_token(self, verify, _app):
        verify.side_effect = Exception("Invalid ID token provided.")
        r = self._post({"token": "abc"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "invalid_token")

    def test_every_error_carries_a_code(self):
        """The app branches on 'code'; a response without one is unusable."""
        body = self._post({}).json()
        self.assertIn("code", body)
        self.assertEqual(body["code"], "missing_token")


class AccountIsolationTests(TestCase):
    """Two Google accounts must never resolve to each other's user row.

    This is the invariant behind the 'previous account's data with the new
    account's picture' report.
    """

    URL = "/api/auth/firebase-login/"

    def _login(self, verify, uid, email, name, picture):
        verify.return_value = {
            "uid": uid, "email": email, "name": name, "picture": picture,
        }
        r = self.client.post(self.URL, {"token": uid}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_distinct_accounts_get_distinct_users_and_tokens(self, verify, _app):
        first = self._login(verify, "uid-one", "one@example.com", "One", "https://img/1.png")
        second = self._login(verify, "uid-two", "two@example.com", "Two", "https://img/2.png")

        self.assertNotEqual(first["user"]["id"], second["user"]["id"])
        self.assertNotEqual(first["access_token"], second["access_token"])
        self.assertEqual(first["user"]["profile_picture"], "https://img/1.png")
        self.assertEqual(second["user"]["profile_picture"], "https://img/2.png")

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_repeat_login_is_stable(self, verify, _app):
        """Signing in again as the same account must not fork a new user."""
        a = self._login(verify, "uid-same", "same@example.com", "Same", "https://img/s.png")
        b = self._login(verify, "uid-same", "same@example.com", "Same", "https://img/s.png")
        self.assertEqual(a["user"]["id"], b["user"]["id"])
        self.assertEqual(User.objects.filter(firebase_uid="uid-same").count(), 1)

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_token_resolves_to_its_own_user(self, verify, _app):
        """The issued JWT must authenticate as that same user, not another."""
        one = self._login(verify, "uid-x", "x@example.com", "X", "")
        two = self._login(verify, "uid-y", "y@example.com", "Y", "")

        c = self.client.get(
            "/api/auth/verify/",
            HTTP_AUTHORIZATION="Bearer " + one["access_token"],
        )
        self.assertEqual(c.status_code, 200)
        self.assertEqual(str(c.json()["user"]["id"]), one["user"]["id"])
        self.assertNotEqual(str(c.json()["user"]["id"]), two["user"]["id"])


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "auth-tests",
    }
})
class LoginCacheInvalidationTests(TestCase):
    """A Google sign-in can change the profile, so the cached copy must go.

    Pinned to LocMemCache because dev settings point CACHES at Redis, which is
    not running on every machine that runs the suite. The behaviour under test
    is the cache.delete call, not the backend.
    """

    URL = "/api/auth/firebase-login/"

    @patch("firebase_admin.get_app")
    @patch("firebase_admin.auth.verify_id_token")
    def test_cached_profile_is_dropped_on_login(self, verify, _app):
        user = User.objects.create(
            email="cached@example.com", display_name="Old Name", username="cached-uid",
        )
        cache.set(f"user_details_{user.id}", {"display_name": "Stale"}, 60)
        self.assertIsNotNone(cache.get(f"user_details_{user.id}"))

        verify.return_value = {
            "uid": "cached-uid", "email": "cached@example.com",
            "name": "Fresh Name", "picture": "https://img/fresh.png",
        }
        r = self.client.post(self.URL, {"token": "cached-uid"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(
            cache.get(f"user_details_{user.id}"),
            "stale profile cache must be cleared so the new name shows",
        )


class RefreshTokenContractTests(TestCase):
    URL = "/api/auth/refresh/"

    def setUp(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        self.refresh = RefreshToken.for_user(
            User.objects.create(email="r@example.com", display_name="R", username="r-uid")
        )

    def _post(self, payload):
        return self.client.post(self.URL, payload, content_type="application/json")

    def test_accepts_refresh_key(self):
        r = self._post({"refresh": str(self.refresh)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access_token", r.json())

    def test_accepts_refresh_token_key(self):
        """Both key spellings are in use by the app."""
        r = self._post({"refresh_token": str(self.refresh)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access_token", r.json())

    def test_missing_token_is_actionable(self):
        r = self._post({})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "missing_refresh_token")

    def test_invalid_token_is_actionable(self):
        r = self._post({"refresh": "not-a-token"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "refresh_invalid")

    def test_refreshed_access_token_authenticates(self):
        r = self._post({"refresh": str(self.refresh)})
        access = r.json()["access_token"]
        me = self.client.get("/api/auth/verify/", HTTP_AUTHORIZATION="Bearer " + access)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["email"], "r@example.com")