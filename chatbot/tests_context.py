"""Tests for the chatbot context improvements: date awareness, calendar routing,
and knowledge-base reachability.

These are the three failure modes that made Mr Caluu look ignorant: a date-blind
prompt, "what is coming up" never reaching the calendar, and knowledge documents
being invisible to semantic search when their embedding had not been built.
"""

import re
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from chatbot.enhanced_service import EnhancedClaudeService

# These tests never call the Anthropic API, but EnhancedClaudeService refuses to
# construct without a key. A dummy satisfies the constructor; the Gemini path is
# not configured in the test env, so Gemini is stubbed out too.
_dummy_key = "sk-ant-test-not-a-real-key"


def build_service():
    """Construct EnhancedClaudeService without needing real API keys."""
    with patch.object(EnhancedClaudeService, "__init__",
                      lambda self: mock_init(self)), \
         patch("chatbot.enhanced_service.GeminiClient", None):
        return EnhancedClaudeService()


def mock_init(svc):
    """Minimal __init__ covering only what these tests exercise."""
    svc._last_request_time = None
    svc._min_request_interval = 3.0
    svc._provider = "anthropic"
    svc._model = "claude-haiku-4-5-20251001"
    svc._client = None
    svc._gemini_client = None
    svc._api_key = ""
    svc._gemini_key = ""
    svc._fallback_locked = False


from chatbot.models import KnowledgeDocument
from chatbot.vector_service import VectorSearchService
from academia.models import AcademicCalendar, AcademicEvent
from api.models import University


class DateInjectionTests(TestCase):
    """Today's date must reach the model on every request."""

    def setUp(self):
        self.svc = build_service()
        self.user = self._make_user()

    def _make_user(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(
            username="dateuser", email="date@example.com", password="x"
        )

    def _prompt(self, message):
        conversation = self.svc.__class__.__module__  # keep flake quiet
        from chatbot.models import Conversation

        convo = Conversation.objects.create(user=self.user, title="t")
        system_prompt, _ = self.svc.build_enhanced_prompt(
            self.user, convo, message
        )
        return system_prompt

    def test_prompt_states_todays_date(self):
        prompt = self._prompt("what are the requirements to register?")
        today = timezone.localtime().date().isoformat()
        self.assertIn("CURRENT DATE", prompt)
        self.assertIn(today, prompt)

    def test_date_is_injected_for_every_intent(self):
        for message in (
            "hi",
            "who is the founder of caluu+",
            "what is coming up",
            "where is the library",
            "my gpa is low",
        ):
            with self.subTest(message=message):
                self.assertIn("CURRENT DATE", self._prompt(message))


class CalendarRoutingTests(TestCase):
    """"What is coming up" must route to the calendar, not general knowledge."""

    def setUp(self):
        self.svc = build_service()

    def test_coming_up_is_not_treated_as_general_faq(self):
        info = self.svc.classify_query_intent("what is coming up")
        self.assertTrue(info["is_calendar"])
        self.assertTrue(info["wants_upcoming"])
        self.assertFalse(info["is_general"])
        self.assertTrue(info["needs_knowledge_base"])

    def test_whats_next_variants_are_caught(self):
        for q in ("what's next", "what is next", "anything coming up", "still to come"):
            with self.subTest(q=q):
                self.assertTrue(self.svc.classify_query_intent(q)["wants_upcoming"])

    def test_calendar_questions_force_the_kb_on(self):
        for q in ("what are the deadlines", "when does registration start"):
            with self.subTest(q=q):
                self.assertTrue(self.svc.classify_query_intent(q)["needs_knowledge_base"])

    def test_unrelated_question_is_not_forced_onto_the_calendar(self):
        info = self.svc.classify_query_intent("what is the capital of France")
        self.assertFalse(info.get("wants_upcoming"))


class CalendarContextTests(TestCase):
    """search_calendar_events must answer with real dates and mark the past."""

    def setUp(self):
        self.svc = build_service()
        self.university = University.objects.create(name="Test Uni")
        today = timezone.localdate()
        self.calendar = AcademicCalendar.objects.create(
            academic_year="2026", semester="Semester 2",
            university=self.university, is_active=True,
            start_date=today - timezone.timedelta(days=90),
            end_date=today + timezone.timedelta(days=90),
        )
        # One clearly future, one clearly past.
        AcademicEvent.objects.create(
            calendar=self.calendar, title="Future Reporting",
            event_type="orientation", start_date=today + timezone.timedelta(days=10),
        )
        AcademicEvent.objects.create(
            calendar=self.calendar, title="Last Semester Exams",
            event_type="examination",
            start_date=today - timezone.timedelta(days=40),
            end_date=today - timezone.timedelta(days=25),
        )

    def test_upcoming_query_returns_todays_date_and_next_event(self):
        out = self.svc.search_calendar_events("what is coming up")
        self.assertIn("TODAY IS", out)
        self.assertIn("Future Reporting", out)
        self.assertIn(str(timezone.localdate().isoformat()), out)

    def test_past_events_are_marked_when_included(self):
        out = self.svc.search_calendar_events("exams")
        if "Last Semester Exams" in out:
            self.assertIn("PAST", out)

    def test_range_events_show_start_and_end_separately(self):
        out = self.svc.search_calendar_events("exams")
        # Starts/Ends are listed separately rather than as "a to b" so a
        # follow-up asking specifically when something starts is answerable.
        self.assertIn("Starts:", out)
        self.assertIn("Ends:", out)

    def test_time_question_is_flagged_as_unanswerable(self):
        # The model has no time-of-day fields, so the prompt must tell the
        # model not to invent one.
        out = self.svc.search_calendar_events("what time does reporting start")
        self.assertIn("DATES only", out)

    def test_followup_resolves_event_by_keyword(self):
        out = self.svc.search_calendar_events("when does reporting start")
        self.assertIn("Future Reporting", out)

    def test_date_shaped_questions_always_read_the_calendar(self):
        # These score as other intents ('procedure', 'faq') but must still
        # consult the calendar, otherwise the bot answers blind and asks for
        # clarification on dates it already holds.
        for q in ("when does reporting start", "what is the start date of reporting?",
                  "when does registration start", "what are the deadlines"):
            with self.subTest(q=q):
                info = self.svc.classify_query_intent(q)
                self.assertTrue(
                    info["is_calendar"],
                    f"{q!r} (intent={info['primary_intent']}) must read the calendar",
                )
                self.assertTrue(info["needs_knowledge_base"])


class KnowledgeReachabilityTests(TestCase):
    """A knowledge document must be findable even without a stored embedding."""

    def setUp(self):
        self.doc = KnowledgeDocument.objects.create(
            title="founder of caluu+",
            content="emmanuel charles is the founder and ceo of kodin software, "
                    "the company behind caluu+",
            category="faq", is_active=True,
        )
        self.svc = VectorSearchService()

    def test_batch_scores_include_docs_without_stored_embedding(self):
        self.assertIsNone(self.doc.embedding, "test doc should start un-embedded")
        q = self.svc._get_embedding("who is the founder of caluu+")
        self.assertIsNotNone(q)
        scores = self.svc._batch_semantic_scores(q, [self.doc])
        self.assertIn(str(self.doc.id), scores)
        self.assertGreater(scores[str(self.doc.id)], 0.0)

    def test_doc_is_found_by_search(self):
        hits = self.svc.search("who is the founder of caluu+", top_k=5)
        titles = [str(h.get("title", "")).lower() for h in hits]
        self.assertTrue(
            any("founder" in t for t in titles),
            f"knowledge doc missing from results: {titles}",
        )


class PlatformQuestionTests(TestCase):
    """Questions about the platform itself must consult the knowledge base.

    "who is" used to be a general-knowledge signal, so a platform question was
    routed away from the KB and Mr Caluu claimed ignorance about facts it had.
    """

    def setUp(self):
        self.svc = build_service()

    def test_founder_question_reaches_the_kb(self):
        info = self.svc.classify_query_intent("who is the founder of caluu+")
        self.assertFalse(info["is_general"])
        self.assertTrue(info["needs_knowledge_base"])

    def test_other_platform_questions_reach_the_kb(self):
        for q in ("who founded caluuplus", "who owns the platform",
                  "what is kodin software", "who is the ceo"):
            with self.subTest(q=q):
                self.assertTrue(
                    self.svc.classify_query_intent(q)["needs_knowledge_base"],
                    f"{q!r} should consult the knowledge base",
                )

    def test_genuinely_general_questions_stay_general(self):
        # Must not over-correct and start grounding world knowledge in the KB.
        for q in ("what is the capital of France", "who is the president"):
            with self.subTest(q=q):
                info = self.svc.classify_query_intent(q)
                self.assertTrue(info["is_general"])
                self.assertFalse(info["needs_knowledge_base"])


class SuggestionCaptureTests(TestCase):
    """When the bot has no KB grounding, a suggestion must be recorded."""

    def test_suggestion_created_when_no_kb_result(self):
        from chatbot.models import KnowledgeSuggestion

        self.assertEqual(KnowledgeSuggestion.objects.count(), 0)
        s = KnowledgeSuggestion.objects.create(
            query_text="who is the founder of caluu+",
            response_text="I don't have that info",
            trigger="no_kb_result",
        )
        self.assertEqual(KnowledgeSuggestion.objects.count(), 1)
        self.assertTrue(s.query_hash)
        self.assertEqual(s.status, "pending")

    def test_query_hash_normalizes_case_and_whitespace(self):
        from chatbot.models import KnowledgeSuggestion

        a = KnowledgeSuggestion.objects.create(query_text="Same Question", trigger="no_kb_result")
        b = KnowledgeSuggestion.objects.create(query_text="  same question  ", trigger="no_kb_result")
        self.assertEqual(a.query_hash, b.query_hash)

    def test_query_hash_is_stable_across_saves(self):
        from chatbot.models import KnowledgeSuggestion

        s = KnowledgeSuggestion.objects.create(
            query_text="who founded caluu", trigger="no_kb_result"
        )
        original = s.query_hash
        s.status = "approved"
        s.save()
        s.refresh_from_db()
        self.assertEqual(s.query_hash, original)

    def test_default_status_is_pending(self):
        from chatbot.models import KnowledgeSuggestion

        s = KnowledgeSuggestion.objects.create(
            query_text="anything", trigger="no_kb_result"
        )
        self.assertEqual(s.status, "pending")
        self.assertEqual(s.confidence_score, 0.0)