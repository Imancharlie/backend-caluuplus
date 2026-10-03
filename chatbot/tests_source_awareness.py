"""Tests for source-awareness: authority labels, ranking, phrasing, and titles.

The knowledge base gained two small fields (source_level, source_attribution)
rather than a new model, so these tests pin the behaviour that matters:
official sources outrank clarifications, lower tiers get a natural qualifier,
official sources get none, and existing documents are unaffected.
"""

from django.test import TestCase

from chatbot.enhanced_service import EnhancedClaudeService
from chatbot.models import KnowledgeDocument, KnowledgeSuggestion
from chatbot.vector_service import VectorSearchService


def build_service():
    """Construct EnhancedClaudeService without real API keys."""
    from unittest.mock import MagicMock, patch

    def mock_init(svc):
        svc._last_request_time = None
        svc._min_request_interval = 3.0
        svc._provider = "anthropic"
        svc._model = "claude-haiku-4-5-20251001"
        svc._client = None
        svc._gemini_client = None
        svc._api_key = ""
        svc._gemini_key = ""
        svc._fallback_locked = False

    with patch.object(EnhancedClaudeService, "__init__", mock_init), \
         patch("chatbot.enhanced_service.GeminiClient", None):
        return EnhancedClaudeService()


class SourceLevelModelTests(TestCase):
    def test_default_is_official(self):
        doc = KnowledgeDocument.objects.create(
            title="Graduation fee policy", content="Fees are as published."
        )
        self.assertEqual(doc.source_level, "official")

    def test_boost_ordering_is_sensible(self):
        levels = ["official", "official_communication",
                  "trusted_clarification", "general"]
        boosts = [KnowledgeDocument(source_level=lv).rank_boost for lv in levels]
        for a, b in zip(boosts, boosts[1:]):
            self.assertGreater(a, b, "authority must rank in descending order")
        # trusted_clarification is the neutral baseline (1.0); official is lifted
        # above it and general dipped slightly below.
        self.assertAlmostEqual(boosts[2], 1.0)
        self.assertGreater(boosts[0], 1.0)
        self.assertLess(boosts[3], 1.0)

    def test_official_needs_no_qualifier(self):
        doc = KnowledgeDocument(source_level="official")
        self.assertEqual(doc.phrasing(), "")

    def test_lower_tiers_produce_a_phrase(self):
        for lv in ("official_communication", "trusted_clarification", "general"):
            with self.subTest(level=lv):
                self.assertTrue(KnowledgeDocument(source_level=lv).phrasing())

    def test_attribution_is_used_when_present(self):
        doc = KnowledgeDocument(
            source_level="trusted_clarification",
            source_attribution="Student Government",
        )
        self.assertIn("Student Government", doc.phrasing())


class SourceRankingTests(TestCase):
    def test_official_outranks_clarification_for_same_query(self):
        official = KnowledgeDocument.objects.create(
            title="Graduation fee",
            content="The graduation fee is paid once during the study period.",
            category="faq",
        )
        clarification = KnowledgeDocument.objects.create(
            title="Graduation fee",
            content="The graduation fee is paid once during the study period.",
            category="faq",
            source_level="trusted_clarification",
            source_attribution="Student Government",
        )
        svc = VectorSearchService()
        hits = svc.search("graduation fee", top_k=5)
        order = [str(h.get("id")) for h in hits]
        if str(official.id) in order and str(clarification.id) in order:
            self.assertLess(order.index(str(official.id)),
                            order.index(str(clarification.id)))

    def test_authority_metadata_reaches_results(self):
        doc = KnowledgeDocument.objects.create(
            title="Student leader clarification on fees",
            content="Fees clarification communicated to students.",
            source_level="trusted_clarification",
            source_attribution="Student Government",
        )
        svc = VectorSearchService()
        hits = svc.search("fees clarification students", top_k=5)
        match = [h for h in hits if h.get("id") == str(doc.id)]
        self.assertTrue(match, "document should be retrievable")
        self.assertEqual(match[0]["source_level"], "trusted_clarification")
        self.assertEqual(match[0]["source_attribution"], "Student Government")


class SourcePromptTests(TestCase):
    """The prompt must label authority and give the model phrasing guidance."""

    def setUp(self):
        self.svc = build_service()

    def _prompt(self, rag_context):
        from django.contrib.auth import get_user_model
        from chatbot.models import Conversation

        user = get_user_model().objects.create_user(
            username="src", email="src@example.com", password="x"
        )
        convo = Conversation.objects.create(user=user, title="t")
        system_prompt, _ = self.svc.build_enhanced_prompt(
            user, convo, "do I pay the graduation fee every year?",
            rag_context=rag_context,
        )
        return system_prompt

    def test_guidance_present_when_knowledge_retrieved(self):
        prompt = self._prompt("KNOWLEDGE BASE DOCUMENT 1\nContent: x")
        self.assertIn("HOW TO PRESENT SOURCES", prompt)
        self.assertIn("OFFICIAL", prompt)
        self.assertIn("TRUSTED CLARIFICATION", prompt)

    def test_guidance_absent_without_knowledge(self):
        prompt = self._prompt("")
        self.assertNotIn("HOW TO PRESENT SOURCES", prompt)

    def test_no_disclaimer_language_is_prescribed(self):
        prompt = self._prompt("KNOWLEDGE BASE DOCUMENT 1\nContent: x")
        lowered = prompt.lower()
        # The model must be told NOT to say these things.
        self.assertIn("do not call it unreliable", lowered)
        self.assertIn("not on every answer", lowered)

    def test_official_source_gets_no_qualifier_line(self):
        svc = VectorSearchService()
        out = svc.format_for_prompt([{
            "title": "Fee schedule", "content": "Fees as published.",
            "category": "policy", "source_level": "official",
            "source_attribution": "", "relevance": 0.9,
        }], max_chars=600)
        self.assertIn("OFFICIAL (University regulation", out)

    def test_clarification_is_labelled_not_disclaimed(self):
        svc = VectorSearchService()
        out = svc.format_for_prompt([{
            "title": "Fee clarification", "content": "Paid once.",
            "category": "faq", "source_level": "trusted_clarification",
            "source_attribution": "Student Government", "relevance": 0.9,
        }], max_chars=600)
        self.assertIn("TRUSTED CLARIFICATION", out)
        self.assertIn("Student Government", out)
        self.assertNotIn("unreliable", out.lower())


class ConversationTitleTests(TestCase):
    def setUp(self):
        self.svc = build_service()

    def test_greetings_produce_no_title(self):
        for greet in ("hi", "Hello!", "hey", "good morning", "yo", "thanks"):
            with self.subTest(greet=greet):
                self.assertEqual(
                    self.svc.summarize_conversation_title(greet, "Hey! How can I help?"),
                    "",
                )

    def test_real_question_becomes_a_title(self):
        t = self.svc.summarize_conversation_title(
            "How do I register for courses?", "Sure...")
        self.assertIn("register", t.lower())
        self.assertLessEqual(len(t), 95)

    def test_greeting_plus_question_uses_the_question(self):
        t = self.svc.summarize_conversation_title(
            "hi, what are the requirements for industrial attachment?", "...")
        self.assertNotIn("hi", t.lower().split()[:1])
        self.assertTrue(t)

    def test_title_is_short(self):
        long_q = ("I would like to know everything there is to understand about "
                  "the process of registering for courses at the university")
        t = self.svc.summarize_conversation_title(long_q, "...")
        self.assertLessEqual(len(t), 95)
        self.assertLess(len(t.split()), 9)

    def test_title_is_sentence_cased_even_with_mid_word_capital(self):
        # Regression: a capital mid-sentence ("do I", "UDSM") previously
        # suppressed the first-letter lift, leaving the whole title lowercase.
        t = self.svc.summarize_conversation_title(
            "how do I register for courses?", "...")
        self.assertTrue(t.startswith("How"), t)

        t = self.svc.summarize_conversation_title(
            "what is UDSM accommodation fee?", "...")
        self.assertTrue(t.startswith("What"), t)

    def test_polite_prefixes_are_stripped(self):
        t = self.svc.summarize_conversation_title(
            "Can you please tell me about resit examinations?", "...")
        self.assertTrue(t.lower().startswith("tell me") or "resit" in t.lower())

    def test_empty_input_returns_empty(self):
        self.assertEqual(self.svc.summarize_conversation_title("", "x"), "")
        self.assertEqual(self.svc.summarize_conversation_title("   ", "x"), "")


class SuggestionSourceLevelTests(TestCase):
    def test_suggestion_defaults_to_general(self):
        s = KnowledgeSuggestion.objects.create(
            query_text="do i pay the graduation fee every year?",
            trigger="no_kb_result",
        )
        self.assertEqual(s.source_level, "general")

    def test_source_level_can_be_marked_trusted(self):
        s = KnowledgeSuggestion.objects.create(
            query_text="fees", trigger="no_kb_result",
            source_level="trusted_clarification",
        )
        s.refresh_from_db()
        self.assertEqual(s.source_level, "trusted_clarification")