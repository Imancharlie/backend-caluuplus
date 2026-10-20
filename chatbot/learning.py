"""
Knowledge-gap detection and capture for Mr Caluu.

This module is the single source of truth for deciding whether a chat turn
revealed a gap in the knowledge base / system data, and for persisting that
gap as a ``KnowledgeSuggestion`` row for staff review.

Why this exists: the previous implementation lived inline in two view methods
(``send_message`` and ``send_message_stream``), the two copies had drifted
apart, and both treated "the RAG search returned nothing" as the only signal of
a gap. Because ``vector_service.search()`` falls back to returning its
best-scoring documents even when every one of them is irrelevant, that signal
almost never fired, so the table stayed empty.

Detection is layered, from cheapest to most reliable:

1. ``is_question`` — chatter ("thanks", "hi") is never a gap.
2. ``is_system_data_query`` — the question touches official/system data
   (policies, fees, dates, results, the student's own record). These are the
   only questions the knowledge base is *authoritative* for, so they are always
   candidates regardless of what ``classify_query_intent`` decided.
3. ``assess_kb_coverage`` — grades the RAG hits as ``hit`` / ``weak`` / ``miss``
   using the relevance score already attached to every search result, instead
   of just checking whether the result list was empty.
4. ``detect_hedging`` — the model admitted it could not ground the answer,
   either by a natural hedge phrase or by the explicit gap-flagging phrase the
   persona layer instructs it to use.

Every decision is traced at INFO level so the pipeline is observable in the
server log rather than failing silently.
"""

import hashlib
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.conf import settings
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


SYSTEM_DATA_SIGNALS: Tuple[str, ...] = (
    'udsm', 'university', 'campus', 'semester', 'academic year', 'academic calendar',
    'exam', 'examination', 'registration', 'register', 'enrol', 'enroll', 'defer',
    'deferral', 'postpone', 'withdraw', 'withdrawal', 'resit', 'supplemental',
    'transcript', 'result', 'results', 'gpa', 'grade', 'grades', 'credit',
    'credits', 'fee', 'fees', 'tuition', 'payment', 'bursary', 'scholarship',
    'hostel', 'accommodation', 'timetable', 'schedule', 'deadline', 'due date',
    'requirement', 'requirements', 'prerequisite', 'prerequisites', 'curriculum',
    'programme', 'program', 'major', 'minor', 'degree', 'faculty', 'department',
    'dean', 'vice chancellor', 'regulation', 'regulations', 'policy', 'policies',
    'procedure', 'procedures', 'guideline', 'guidelines', 'rule', 'rules',
    'syllabus', 'assignment', 'course', 'courses', 'lecturer', 'professor',
    'graduation', 'graduating', 'transcript', 'provisional', 'academic integrity',
    'plagiarism', 'cheating', 'my gpa', 'my result', 'my fee', 'my semester',
    'my course', 'my record', 'my progress', 'my transcript', 'my marks',
    'my registration', 'my timetable', 'my calendar', 'what do i owe',
)

SELF_RECORD_SIGNALS: Tuple[str, ...] = (
    'my gpa', 'my result', 'my results', 'my marks', 'my fee', 'my fees',
    'my semester', 'my course', 'my courses', 'my record', 'my transcript',
    'my progress', 'my registration', 'my timetable', 'my calendar',
    'my hostel', 'my bursary', 'my scholarship', 'what do i owe', 'do i owe',
    'have i passed', 'am i registered', 'what is on my', 'whats on my',
)

HEDGE_PHRASES: Tuple[str, ...] = (
    "i don't know",
    "i do not know",
    "i'm not sure",
    "i am not sure",
    "im not sure",
    "not certain",
    "i couldn't find",
    "i could not find",
    "i can't find",
    "i cannot find",
    "can't find that",
    "cannot find that",
    "no information",
    "no record of that",
    "not in my records",
    "don't have information",
    "do not have that information",
    "not in the knowledge base",
    "outside what i know",
    "outside of what i know",
    "i can't answer",
    "i cannot answer",
    "can't answer that",
    "i don't have access",
    "i do not have access",
    "i lack",
    "i couldn't confirm",
    "i can't confirm",
    "cannot confirm",
    "not something i can confirm",
    "i don't have that specific",
    "don't have that specific",
    "i don't see that in",
    "i do not see that in",
    "isn't showing in",
    "is not showing in",
    "nothing on file",
    "not on your record",
    "not on file for you",
    "beyond what i can see",
    "not the full picture",
    "isn't the full picture",
    "is not the full picture",
    "not a complete picture",
    "only part of the picture",
    "can't verify that",
    "cannot verify that",
    "unable to verify",
)

GAP_FLAG_PHRASES: Tuple[str, ...] = (
    "flagging this",
    "flag this",
    "flag it",
    "let me flag",
    "passing this along",
    "pass this along",
    "log this for",
    "logging this for",
    "notifying the office",
    "i've noted this for",
    "i have noted this for",
    "adding this to the",
    "sent this to the office",
    "raised this with the office",
)

ACTIONABLE_PHRASES: Tuple[str, ...] = (
    "confirm with",
    "check with",
    "verify with",
    "contact the",
    "reach out to the",
    "inquire at",
    "ask the office",
    "the office can confirm",
)

QUESTION_WORDS = (
    'who', 'what', 'when', 'where', 'why', 'how', 'can', 'could', 'should',
    'would', 'will', 'is', 'are', 'am', 'do', 'does', 'did', 'which', 'whom',
    'whose', 'tell me about', 'explain',
)

CHATTER_PHRASES: Tuple[str, ...] = (
    'hi', 'hey', 'hello', 'yo', 'sup', 'thanks', 'thank you', 'thx', 'ok',
    'okay', 'cool', 'nice', 'lol', 'haha', 'good morning', 'good evening',
    'good afternoon', 'bye', 'goodbye', 'see you', 'no', 'yes', 'sure',
    'got it', 'understood', 'makes sense', 'same', 'wow', 'perfect', 'great',
)

_KB_HIT_MIN_RELEVANCE = 0.20
_KB_WEAK_MIN_RELEVANCE = 0.08
_MAX_KB_GAPS = 20


def _setting(name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def _verbose() -> bool:
    return bool(_setting('CHATBOT_LEARNING_VERBOSE', True))


def _trace(message: str) -> None:
    if _verbose():
        logger.info(f"[knowledge-gap] {message}")


def is_chatter(text: str) -> bool:
    """True for greetings/acknowledgements that can never be knowledge gaps."""
    stripped = re.sub(r"[^\w\s']", "", (text or "").lower()).strip()
    if not stripped:
        return True
    if len(stripped.split()) <= 4:
        return any(stripped == phrase or stripped.startswith(phrase + " ")
                   for phrase in CHATTER_PHRASES)
    return False


def is_question(text: str) -> bool:
    """True when the message is an actual ask rather than small talk."""
    if not text or is_chatter(text):
        return False
    if re.search(r"[?؟]", text):
        return True
    return bool(re.search(r"\b(" + "|".join(QUESTION_WORDS) + r")\b", text.lower()))


def is_system_data_query(text: str) -> bool:
    """True when the question touches official university/system data."""
    lowered = (text or "").lower()
    return any(signal in lowered for signal in SYSTEM_DATA_SIGNALS)


def is_self_record_query(text: str) -> bool:
    """True when the question is about this student's own record."""
    lowered = (text or "").lower()
    return any(signal in lowered for signal in SELF_RECORD_SIGNALS)


def detect_hedging(text: str) -> Optional[str]:
    """Return the phrase that proves the model could not ground its answer."""
    lowered = (text or "").lower()
    for phrase in GAP_FLAG_PHRASES:
        if phrase in lowered:
            return phrase
    for phrase in HEDGE_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def detect_unverified_advice(text: str) -> Optional[str]:
    """Return a phrase showing the model pushed the student to verify elsewhere."""
    lowered = (text or "").lower()
    for phrase in ACTIONABLE_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def assess_kb_coverage(search_results: Optional[Iterable[Dict[str, Any]]]) -> Tuple[str, float]:
    """
    Grade how well the knowledge base covered a question.

    ``vector_service.search()`` never returns an empty list for a non-empty
    index — it falls back to its best-scoring documents regardless of how
    irrelevant they are. Judging coverage purely on emptiness therefore
    reported "covered" for almost every question. Grading on the relevance
    score that each result already carries restores the missing signal.
    """
    if not search_results:
        return 'miss', 0.0

    best = 0.0
    for result in search_results:
        if not isinstance(result, dict):
            continue
        try:
            best = max(best, float(result.get('relevance') or 0.0))
        except (TypeError, ValueError):
            continue

    hit_min = float(_setting('CHATBOT_KB_HIT_MIN_RELEVANCE', _KB_HIT_MIN_RELEVANCE))
    weak_min = float(_setting('CHATBOT_KB_WEAK_MIN_RELEVANCE', _KB_WEAK_MIN_RELEVANCE))
    if best >= hit_min:
        return 'hit', best
    if best >= weak_min:
        return 'weak', best
    return 'miss', best


def _normalized_hash(query: str) -> str:
    normalized = " ".join((query or "").lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def record_knowledge_gap(
    conversation,
    query: str,
    trigger: Optional[str],
    coverage: str,
    best_relevance: float,
) -> None:
    """Append the gap to the conversation's analytics trail (capped)."""
    from .models import ConversationAnalytics

    analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=conversation)
    gaps: List[Dict[str, Any]] = list(analytics.knowledge_gaps or [])
    entry = {
        'query': (query or "")[:200],
        'reason': trigger or 'no_kb_result',
        'kb_coverage': coverage,
        'kb_relevance': round(best_relevance, 3),
        'at': timezone.now().isoformat(),
    }
    if any(gap.get('query', '') == entry['query'] for gap in gaps):
        return
    gaps.append(entry)
    analytics.knowledge_gaps = gaps[-_MAX_KB_GAPS:]
    analytics.save(update_fields=['knowledge_gaps'])


def capture_knowledge_suggestion(
    *,
    query: str,
    response: str,
    conversation,
    user,
    intent_info: Optional[Dict[str, Any]] = None,
    search_results: Optional[Iterable[Dict[str, Any]]] = None,
    rag_context: str = '',
    source: str = 'unknown',
) -> Dict[str, Any]:
    """
    Detect a knowledge gap in one chat turn and persist it for staff review.

    Returns a result dict describing the decision so callers (and tests) can
    assert on why a suggestion was or was not stored.
    """
    from .models import KnowledgeSuggestion

    query = (query or "").strip()
    response = (response or "").strip()

    if not query:
        _trace(f"skip: empty query (source={source})")
        return {'stored': False, 'reason': 'empty_query'}

    if not is_question(query):
        _trace(f"skip: not a question -> '{query[:60]}' (source={source})")
        return {'stored': False, 'reason': 'not_a_question'}

    intent_info = intent_info or {}
    needs_kb = bool(intent_info.get('needs_knowledge_base', True))
    system_data = is_system_data_query(query)
    self_record = is_self_record_query(query)
    coverage, best_relevance = assess_kb_coverage(search_results)
    hedge = detect_hedging(response)
    advice = None if hedge else detect_unverified_advice(response)

    _trace(
        f"evaluate '{query[:60]}' (source={source}) "
        f"needs_kb={needs_kb} system_data={system_data} self_record={self_record} "
        f"coverage={coverage} best_relevance={best_relevance:.3f} "
        f"hedge={hedge!r} advice={advice!r} rag_chars={len(rag_context or '')}"
    )

    expects_system_data = needs_kb or system_data or self_record
    if not expects_system_data:
        _trace(f"skip: general-knowledge question, KB not authoritative (source={source})")
        return {'stored': False, 'reason': 'general_question', 'coverage': coverage}

    kb_miss = coverage == 'miss' or (system_data and coverage == 'weak')
    uncertain = bool(hedge) or (coverage == 'weak' and system_data) or (
        coverage == 'hit' and advice is not None and system_data
    )

    if not kb_miss and not uncertain:
        _trace(
            f"skip: KB answered it (coverage={coverage} "
            f"relevance={best_relevance:.3f}) (source={source})"
        )
        return {
            'stored': False,
            'reason': 'kb_covered',
            'coverage': coverage,
            'best_relevance': best_relevance,
        }

    if kb_miss:
        trigger = 'no_kb_result'
        confidence_score = 0.0 if coverage == 'miss' else 0.2
    else:
        trigger = 'low_confidence'
        confidence_score = 0.3

    query_hash = _normalized_hash(query)
    try:
        suggestion, created = KnowledgeSuggestion.objects.get_or_create(
            query_hash=query_hash,
            defaults={
                'query_text': query,
                'response_text': response,
                'trigger': trigger,
                'confidence_score': confidence_score,
                'conversation': conversation,
                'user': user,
            },
        )
    except Exception as exc:
        logger.error(f"[knowledge-gap] failed to store suggestion for '{query[:60]}': {exc}")
        return {'stored': False, 'reason': 'db_error', 'error': str(exc)}

    if created:
        logger.info(
            f"📝 KnowledgeSuggestion CREATED [{trigger}] coverage={coverage} "
            f"relevance={best_relevance:.3f} source={source} query='{query[:70]}'"
        )
    else:
        KnowledgeSuggestion.objects.filter(pk=suggestion.pk).update(
            occurrence_count=F('occurrence_count') + 1,
            last_seen_at=timezone.now(),
            response_text=response or suggestion.response_text,
        )
        suggestion.refresh_from_db(fields=['occurrence_count', 'last_seen_at'])
        logger.info(
            f"📝 KnowledgeSuggestion REPEAT #{suggestion.occurrence_count} "
            f"[{trigger}] coverage={coverage} relevance={best_relevance:.3f} "
            f"source={source} query='{query[:70]}'"
        )

    try:
        record_knowledge_gap(conversation, query, trigger, coverage, best_relevance)
    except Exception as exc:
        logger.warning(f"[knowledge-gap] analytics trail update failed: {exc}")

    return {
        'stored': True,
        'created': created,
        'id': str(suggestion.id),
        'trigger': trigger,
        'coverage': coverage,
        'best_relevance': best_relevance,
        'hedge': hedge,
        'reason': 'stored',
    }


def capture_negative_feedback(
    *,
    query: str,
    response: str,
    conversation,
    user,
    rating: int,
) -> Optional[Any]:
    """Store (or bump) a suggestion for a low-rated answer."""
    from .models import KnowledgeSuggestion

    query = (query or "").strip()
    response = (response or "").strip()

    try:
        if query:
            query_hash = _normalized_hash(query)
            suggestion, created = KnowledgeSuggestion.objects.get_or_create(
                query_hash=query_hash,
                defaults={
                    'query_text': query,
                    'response_text': response,
                    'trigger': 'negative_rating',
                    'confidence_score': round(float(rating) / 5.0, 2),
                    'conversation': conversation,
                    'user': user,
                },
            )
            if not created:
                KnowledgeSuggestion.objects.filter(pk=suggestion.pk).update(
                    occurrence_count=F('occurrence_count') + 1,
                    last_seen_at=timezone.now(),
                    response_text=response or suggestion.response_text,
                )
                suggestion.refresh_from_db(fields=['occurrence_count', 'last_seen_at'])
        else:
            suggestion = KnowledgeSuggestion.objects.create(
                query_text='(feedback without a recoverable question)',
                response_text=response,
                trigger='negative_rating',
                confidence_score=round(float(rating) / 5.0, 2),
                conversation=conversation,
                user=user,
            )
            created = True
    except Exception as exc:
        logger.error(f"[knowledge-gap] failed to store negative feedback: {exc}")
        return None

    if created:
        logger.info(
            f"📝 KnowledgeSuggestion CREATED [negative_rating] {rating}/5 "
            f"query='{query[:70]}'"
        )
    else:
        logger.info(
            f"📝 KnowledgeSuggestion REPEAT #{suggestion.occurrence_count} "
            f"[negative_rating] {rating}/5 query='{query[:70]}'"
        )
    return suggestion
