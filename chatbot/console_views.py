"""Template-based chat console for Mr. Caluu, restricted to superusers.

A small server-rendered front end for talking to the chatbot and walking through
conversation history, sitting alongside the JSON API in ``views.py``. The page
is a thin client: it renders an empty shell and then calls the existing
``/api/chatbot/conversations/...`` endpoints from JavaScript, so there is exactly
one implementation of the chat pipeline.

Why a JWT is handed to the page
-------------------------------
``production.py`` sets ``DEFAULT_AUTHENTICATION_CLASSES`` to
``OptionalJWTAuthentication`` only -- there is no ``SessionAuthentication``. A
Django session login therefore does *not* authenticate API calls, so the console
mints a short-lived access token server-side and injects it into the page.
Adding ``SessionAuthentication`` to the global list would change auth behaviour
for the entire public API, which is a much bigger blast radius than this page
needs.

Login uses the same email+password flow as the admin dashboard, and the same
``is_superuser`` gate, so an admin who can reach /admin/ can reach this.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count
from django.shortcuts import redirect, render

from .models import Conversation

logger = logging.getLogger(__name__)

CONSOLE_URL = "chatbot-console"
LOGIN_URL = "chatbot-console-login"


def console_login(request):
    """Superuser-only sign-in for the chat console."""
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect(CONSOLE_URL)

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""

        user = authenticate(request, username=email, password=password)
        if user is None:
            return render(
                request,
                "chatbot_console/login.html",
                {"error": "Invalid email or password."},
            )
        if not user.is_superuser:
            return render(
                request,
                "chatbot_console/login.html",
                {
                    "error": "Mr. Caluu's console is restricted to superusers. "
                    "This account does not have admin privileges."
                },
            )

        login(request, user)
        messages.success(request, f"Signed in as {user.email}.")
        return redirect(CONSOLE_URL)

    return render(request, "chatbot_console/login.html")


def console_logout(request):
    logout(request)
    messages.success(request, "Signed out of the chat console.")
    return redirect(LOGIN_URL)


def console_home(request):
    """Render the chat shell, pre-seeded with a token and the history list.

    The history list is inlined so the sidebar paints immediately instead of
    after a round trip -- that perceived latency is exactly what makes a chat UI
    feel sluggish on mobile data.
    """
    if not request.user.is_authenticated:
        return redirect(LOGIN_URL)
    if not request.user.is_superuser:
        messages.error(request, "Superuser access is required for the chat console.")
        return redirect(LOGIN_URL)

    # Minted here rather than accepting one from the client: the token is only
    # ever handed to a session we just authenticated as a superuser.
    try:
        from rest_framework_simplejwt.tokens import RefreshToken

        access_token = str(RefreshToken.for_user(request.user).access_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not mint console JWT for %s: %s", request.user, exc)
        return render(
            request,
            "chatbot_console/login.html",
            {"error": "Could not start a console session. Please try again."},
        )

    conversations = list(
        Conversation.objects.filter(user=request.user)
        .prefetch_related("messages")
        .only("id", "title", "is_active", "updated_at", "total_tokens", "total_cost_tsh")
    )

    # One aggregate query for the message counts, rather than len() per row.
    counts = {
        row["id"]: row["n"]
        for row in (
            Conversation.objects.filter(user=request.user)
            .values("id")
            .annotate(n=Count("messages"))
        )
    }
    histories = [
        {
            "id": str(c.id),
            "title": c.title or "New Conversation",
            "is_active": c.is_active,
            "updated_at": c.updated_at.isoformat(),
            "message_count": counts.get(c.id, 0),
            "total_tokens": c.total_tokens,
        }
        for c in conversations
    ]

    return render(
        request,
        "chatbot_console/chat.html",
        {
            "access_token": access_token,
            # Serialised here rather than in the template: datetime objects are
            # not JSON-serialisable, and escapejs alone would produce invalid JSON.
            "histories_json": json.dumps(histories),
            "operator": request.user.email or request.user.get_username(),
        },
    )