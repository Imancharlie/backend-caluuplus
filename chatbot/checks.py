"""
Deployment safety checks for Mr. Caluu's AI provider credentials.

``EnhancedClaudeService`` raises ``RuntimeError`` when no provider is
configured, but only lazily — on the first chat request. That means a server
whose environment lost ``ANTHROPIC_API_KEY`` boots happily, passes health
checks, and then 500s on every message a student sends.

These checks move that failure forward to ``manage.py check``, which the deploy
pipeline runs before restarting the service. With ``DEBUG=False`` a missing
Anthropic key is a hard ``Error`` (blocking the deploy and triggering the
pipeline's auto-rollback); with ``DEBUG=True`` it is only a ``Warning`` so
local development is not blocked.
"""

import os

from django.conf import settings
from django.core.checks import Error, Warning, register

ANTHROPIC_HINT = (
    "Set ANTHROPIC_API_KEY in the .env file next to manage.py (local dev) or in "
    "the service environment (server). Mr. Caluu cannot answer without it."
)

GEMINI_HINT = (
    "Set GEMINI_API_KEY in the .env file next to manage.py (local dev) or in "
    "the service environment (server). Mr. Caluu cannot answer without it."
)


def _configured(name):
    value = getattr(settings, name, "") or os.getenv(name, "")
    return bool(str(value).strip())


@register()
def chatbot_ai_credentials(app_configs, **kwargs):
    issues = []
    is_production = not getattr(settings, "DEBUG", False)

    has_anthropic = _configured("ANTHROPIC_API_KEY")
    has_gemini = _configured("GEMINI_API_KEY")

    if not has_anthropic and not has_gemini:
        message = (
            "No AI provider is configured, so every Mr. Caluu message will fail "
            f"with a 500. {ANTHROPIC_HINT} {GEMINI_HINT}"
        )
        issues.append(
            Error(message, id="chatbot.E001")
            if is_production
            else Warning(message, id="chatbot.W001")
        )
        return issues

    if not has_anthropic:
        message = (
            "ANTHROPIC_API_KEY is not set, so Mr. Caluu falls back to Gemini. "
            "Behaviour differs between the two providers (model, latency, "
            f"web-search support). {ANTHROPIC_HINT}"
        )
        issues.append(
            Error(message, id="chatbot.E002")
            if is_production
            else Warning(message, id="chatbot.W002")
        )

    return issues
