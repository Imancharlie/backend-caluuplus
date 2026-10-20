import re as regex_module
import time
import json
import logging
from django.db import transaction
from django.db.models import Sum, Avg, Count
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Conversation, Message, ChatHistory
from .serializers import (
    ConversationSerializer,
    ConversationListSerializer,
    MessageSerializer,
    ChatHistorySerializer,
    KnowledgeSuggestionSerializer,
)
from .enhanced_service import EnhancedClaudeService
from .vector_service import VectorSearchService
from .anthropic_service import AnthropicService

logger = logging.getLogger(__name__)


_UNBILLABLE_REPLY_STARTS = (
    "i'm having trouble",
    "i'm experiencing a configuration",
    "i'm currently at my usage limit",
    "i'm hitting my usage limit",
    "the ai service is temporarily unavailable",
    "sorry, i couldn't generate",
    "i'm having a little trouble",
)


def _opening_user_message(conversation, *, already_saved):
    """The first thing a person sends in a conversation is free."""
    count = conversation.messages.filter(role="user").count()
    return count <= (1 if already_saved else 0)


def _reply_is_billable(text):
    """Charge only a real answer. Errors, empty text, and connection fallbacks are free."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    return not cleaned.startswith(_UNBILLABLE_REPLY_STARTS)


def _charge_mr_caluu(user, assistant_msg, reply_text, opening_message):
    if opening_message or assistant_msg is None or not _reply_is_billable(reply_text):
        return
    try:
        from tokens import services as token_service
        token_service.consume(
            user,
            "MR_CALUU_MESSAGE",
            reference_key=f"mrcaluu:{assistant_msg.id}",
            description="Mr Caluu message",
            initiated_by="chatbot",
        )
    except Exception as exc:
        logger.warning("Mr Caluu token consumption skipped for user %s: %s", user.id, exc)


def _mr_caluu_token_block(user):
    """Refuse the reply before the model runs when the wallet cannot pay.

    An inactive or zero-cost rule lets the message through.
    """
    from tokens.services import has_balance_for

    allowed, _cost = has_balance_for(user, rule_key="MR_CALUU_MESSAGE")
    if allowed:
        return None
    return Response(
        {
            "detail": "You've run out of tokens. Get tokens to keep chatting with Mr Caluu.",
            "code": "insufficient_balance",
        },
        status=status.HTTP_402_PAYMENT_REQUIRED,
    )


# Alias for clarity - use 're' throughout the file
re = regex_module

# Singleton services — initialized once, reused across all requests.
# Eliminates per-request client handshake + model-load overhead.
_enhanced_service: EnhancedClaudeService | None = None
_vector_service: VectorSearchService | None = None

# GET /conversations/active/ is polled whenever the chat panel opens, so it
# returns only the most recent page of messages instead of the whole thread.
ACTIVE_MESSAGE_PAGE = 50


def get_enhanced_service() -> EnhancedClaudeService:
    global _enhanced_service
    if _enhanced_service is None:
        _enhanced_service = EnhancedClaudeService()
    return _enhanced_service


def get_vector_service() -> VectorSearchService:
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorSearchService()
    return _vector_service


class ChatbotViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return ConversationListSerializer
        return ConversationSerializer

    def get_queryset(self):
        queryset = Conversation.objects.filter(user=self.request.user)
        if self.action == 'list':
            return queryset
        return queryset.prefetch_related('messages')

    def get_serializer_class(self):
        # The list endpoint must NOT embed every message of every conversation:
        # ConversationSerializer nests the full history, so one long thread turned
        # the list payload into ~100KB and it grows without bound as a student
        # accumulates messages. Lists get the light serializer; clients fetch
        # history from /messages/ or the detail endpoint.
        if self.action == "list":
            return ConversationListSerializer
        return ConversationSerializer

    def list(self, request, *args, **kwargs):
        # Paginate the list so one account with many conversations cannot return
        # an unbounded response.
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        title = request.data.get("title") or "New Conversation"
        convo = Conversation.objects.create(user=request.user, title=title, is_active=True)
        serializer = ConversationSerializer(convo)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _detect_quick_intent(self, text: str) -> str | None:
        """Return a quick intent key or None - ONLY for greeting.
        All other queries go to AI for better, contextual responses.
        """
        if not text:
            return None
        lowered = text.strip().lower()

        # ONLY greeting - and only if very short and starts with greeting word
        if len(lowered) <= 15 and re.match(r"^(hi|hello|hey)\b", lowered):
            return "greeting"

        # Everything else goes to AI for intelligent handling
        return None

    def _validate_and_sanitize_input(self, message: str) -> bool:
        """Validate message input and return True if valid"""

        # Check message length (max 2000 characters)
        if len(message) > 2000:
            return False

        # Check for minimum length (at least 1 character after strip)
        if len(message.strip()) < 1:
            return False

        # Check for suspicious patterns (potential injection attempts)
        suspicious_patterns = [
            r'<script[^>]*>.*?</script>',  # Script tags
            r'javascript:',  # JavaScript protocol
            r'on\w+\s*=',  # Event handlers
            r'<iframe[^>]*>.*?</iframe>',  # Iframe tags
            r'<object[^>]*>.*?</object>',  # Object tags
            r'<embed[^>]*>',  # Embed tags
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, message, re.IGNORECASE | re.DOTALL):
                return False

        return True

    def _sanitize_message(self, message: str) -> str:
        """Sanitize user message to prevent injection"""
        import html
        
        # HTML escape to prevent XSS
        sanitized = html.escape(message)
        
        # Remove any potential script tags
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove any event handlers
        sanitized = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)

        return sanitized.strip()

    @action(detail=True, methods=["post"], url_path="send_message")
    def send_message(self, request, pk=None):
        """Enhanced send_message with memory, RAG, and token safety.

        LLM + RAG work happens OUTSIDE any transaction. Only short DB writes
        are wrapped in atomic blocks, so slow AI calls never hold SQLite locks.
        """
        start_time = time.time()
        conversation = self.get_object()

        # Gate: admin co-pilot mode disables the automatic bot pipeline
        if conversation.mode == "admin_copilot":
            return Response(
                {"detail": "An advisor is handling this conversation. Please wait for their response."},
                status=status.HTTP_200_OK,
            )

        # Validate input
        raw_message = request.data.get("message", "")
        if not self._validate_and_sanitize_input(raw_message):
            logger.warning(f"Invalid message format from user {request.user.id}")
            return Response(
                {"detail": "Invalid message format or content"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sanitize the message
        sanitized_message = self._sanitize_message(raw_message)

        if not sanitized_message:
            logger.warning(f"Empty message after sanitization from user {request.user.id}")
            return Response(
                {"detail": "Message cannot be empty"},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"Processing message from user {request.user.id}, length: {len(sanitized_message)}")

        opening_message = _opening_user_message(conversation, already_saved=False)
        if not opening_message:
            blocked = _mr_caluu_token_block(request.user)
            if blocked is not None:
                return blocked

        # Save user message (short transaction, no LLM)
        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                role="user",
                content=sanitized_message
            )

        # Initialize services (module-level singletons, not rebuilt per request)
        enhanced_service = get_enhanced_service()
        vector_service = get_vector_service()

        quick = False
        ai_response = None
        assistant_msg = None
        intent_info = None
        rag_context = ""
        search_results = None

        # Smart response prioritization: quick response saves tokens & cost
        message_count = conversation.messages.count()
        quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)

        if quick_type:
            quick = enhanced_service.get_quick_response(quick_type, request.user)
            if quick:
                logger.info(f"Using quick {quick_type} response for user {request.user.id} - free, no API call")
                with transaction.atomic():
                    assistant_msg = Message.objects.create(
                        conversation=conversation,
                        role="assistant",
                        content=quick,
                        tokens_used=0,
                        cost_tsh=0.0
                    )
                    conversation.save(update_fields=["updated_at"])
            else:
                # No quick answer available for this intent: fall through to the
                # LLM path rather than replying with nothing.
                quick = False
                quick_type = None

        if not quick_type:
            # ---- LLM path: ALL RAG + LLM work happens OUTSIDE any transaction ----
            logger.info(f"Generating AI response for user {request.user.id}")

            intent_info = enhanced_service.classify_query_intent(sanitized_message)
            needs_kb = intent_info.get('needs_knowledge_base', True)
            primary_intent = intent_info.get('primary_intent', 'faq')

            navigation_context = ""

            try:
                university_id = None
                if hasattr(request.user, 'student_profile') and request.user.student_profile:
                    university_id = request.user.student_profile.university_id

                if needs_kb:
                    search_results = vector_service.search(
                        sanitized_message,
                        top_k=5 if intent_info.get('is_critical') else 3,
                        university_id=university_id
                    )
                    if search_results:
                        rag_context = vector_service.format_for_prompt(
                            search_results,
                            max_chars=800 if intent_info.get('is_critical') else 600
                        )
                        logger.info(f"📚 KNOWLEDGE BASE USED - {len(search_results)} documents")
                    else:
                        logger.warning(f"⚠️ NO KNOWLEDGE BASE RESULTS for '{sanitized_message}'")

                if primary_intent == 'navigation':
                    nav_results = vector_service.search_navigation(sanitized_message, top_k=3)
                    if nav_results:
                        nav_lines = []
                        for nav in nav_results:
                            nav_lines.append(f"- {nav['name']}: {nav['description']} [LINK:{nav['route']}]")
                        navigation_context = "\n".join(nav_lines)

                # Entity-specific searches (articles, opportunities, calendar events)
                if primary_intent == 'articles':
                    article_context = enhanced_service.search_articles(sanitized_message, university_id)
                    if article_context:
                        rag_context += f"\n\nRELEVANT ARTICLES:\n{article_context}"
                        logger.info(f"📰 ARTICLES SEARCH USED")

                elif primary_intent == 'opportunities':
                    opp_context = enhanced_service.search_opportunities(sanitized_message, university_id)
                    if opp_context:
                        rag_context += f"\n\nRELEVANT OPPORTUNITIES:\n{opp_context}"
                        logger.info(f"💼 OPPORTUNITIES SEARCH USED")

                elif primary_intent == 'calendar_events':
                    calendar_context = enhanced_service.search_calendar_events(sanitized_message, university_id)
                    if calendar_context:
                        rag_context += f"\n\nRELEVANT CALENDAR EVENTS:\n{calendar_context}"
                        logger.info(f"📅 CALENDAR EVENTS SEARCH USED")

                # "What is coming up / what's next" classifies as plain 'faq',
                # so the calendar branch above never ran for those. Read it
                # whenever the intent layer flagged the query as date-shaped.
                elif intent_info.get('is_calendar') or intent_info.get('wants_upcoming'):
                    calendar_context = enhanced_service.search_calendar_events(
                        sanitized_message, university_id,
                        top_k=6 if intent_info.get('wants_upcoming') else 3,
                    )
                    if calendar_context:
                        rag_context += (
                            "\n\nUPCOMING ACADEMIC DATES (from the university "
                            f"calendar):\n{calendar_context}"
                        )
                        logger.info("📅 UPCOMING DATES INJECTED")
            except Exception as e:
                logger.warning(f"RAG/navigation search failed for user {request.user.id}: {str(e)}")

            # LLM call (no DB write inside) — pass pre-classified intent
            ai_response = enhanced_service.get_enhanced_response(
                sanitized_message,
                request.user,
                conversation,
                rag_context,
                navigation_context,
                intent_info=intent_info,
            )

            # Add upcoming events alert naturally
            try:
                upcoming_alert = enhanced_service.get_upcoming_events_alert(request.user)
                if upcoming_alert:
                    ai_response.text = f"{ai_response.text}\n\n{upcoming_alert}"
            except Exception as e:
                logger.debug(f"Failed to add upcoming events alert: {e}")

            # Update analytics (separate, best-effort)
            try:
                from .models import ConversationAnalytics
                analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=conversation)
                analytics.query_intent = primary_intent
                analytics.update_metrics(api_call=True)
                analytics.save()
            except Exception as e:
                logger.debug(f"Error updating analytics: {e}")

            # Save assistant message (short transaction, no LLM)
            with transaction.atomic():
                assistant_msg = Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=ai_response.text,
                    tokens_used=ai_response.tokens_used,
                    cost_tsh=ai_response.cost_tsh
                )

                # Name the conversation after its first substantive exchange.
                # A greeting produces no title, so the title is set on the first
                # message that actually asks something.
                updates = ["updated_at"]
                if not conversation.title or conversation.title == "New Conversation":
                    derived = enhanced_service.summarize_conversation_title(
                        sanitized_message, ai_response.text
                    )
                    if derived:
                        conversation.title = derived
                        updates.append("title")
                        logger.info(f"Conversation titled: {derived!r}")
                conversation.save(update_fields=updates)

            logger.info(f"AI response saved for user {request.user.id}, tokens: {ai_response.tokens_used}")

        # Memory update after main flow (best-effort, never fails the request)
        if ai_response is not None:
            try:
                enhanced_service.update_memory(request.user, conversation, ai_response)
                logger.info(f"Memory updated for user {request.user.id}")
            except Exception as e:
                logger.error(f"Memory update failed for user {request.user.id}: {e}")

            # Personal memory candidates (Phase 2) — extract from the same LLM response
            try:
                candidates = getattr(ai_response, 'memory_candidates', None)
                if candidates and assistant_msg is not None:
                    enhanced_service._process_memory_candidates(
                        request.user, assistant_msg, candidates
                    )
            except Exception as e:
                logger.error(f"Memory candidate extraction failed for user {request.user.id}: {e}")

        # Charge only a completed answer. The first message, quick replies,
        # and connection or error fallbacks stay free.
        if not quick:
            reply_text = ai_response.text if ai_response is not None else ""
            _charge_mr_caluu(
                request.user,
                assistant_msg,
                reply_text,
                _opening_user_message(conversation, already_saved=True),
            )

        # Capture learning suggestions (Phase 5) — shared detector, never fatal.
        if ai_response is not None:
            try:
                from .learning import capture_knowledge_suggestion
                capture_knowledge_suggestion(
                    query=sanitized_message,
                    response=ai_response.text,
                    conversation=conversation,
                    user=request.user,
                    intent_info=intent_info,
                    search_results=search_results,
                    rag_context=rag_context,
                    source="send_message",
                )
            except Exception as e:
                logger.error(f"Knowledge suggestion capture failed for user {request.user.id}: {e}")
        else:
            logger.info(
                f"[knowledge-gap] skip: quick response, no answer evaluated "
                f"(user {request.user.id}, '{sanitized_message[:50]}')"
            )

        # get_queryset() prefetches 'messages', so self.get_object() handed us a
        # conversation whose related cache was filled *before* this request wrote
        # the user turn and the assistant reply. Serialising that stale cache
        # returns "messages": [] -- HTTP 200 with no content -- which made any
        # client rendering response.messages[-1] spin forever. Dropping the
        # cache makes the serializer re-query and see both new rows.
        conversation._prefetched_objects_cache = {}

        serializer = ConversationSerializer(conversation)
        # The conversation payload carries the full message list, but clients need
        # the new reply and its cost up front (see API_ENDPOINTS_GUIDE.md).
        # ``messages[-1]`` is the assistant message just saved above.
        messages = serializer.data.get("messages") or []
        payload = dict(serializer.data)
        payload["reply"] = messages[-1]["content"] if messages else ""
        payload["tokens_used"] = messages[-1].get("tokens_used", 0) if messages else 0
        payload["cost_tsh"] = messages[-1].get("cost_tsh", 0.0) if messages else 0.0
        payload["quick_response"] = bool(quick)
        payload["response_time"] = round(time.time() - start_time, 3)
        total_time = time.time() - start_time
        logger.info(f"Message processing completed for user {request.user.id} in {total_time:.2f}s")

        return Response(payload)

    @action(detail=True, methods=["post"], url_path="send_message_stream")
    def send_message_stream(self, request, pk=None):
        """SSE streaming endpoint — webapp subscribes instead of blocking on one long call."""
        conversation = self.get_object()

        # Gate: admin co-pilot mode disables the automatic bot pipeline
        if conversation.mode == "admin_copilot":
            return Response(
                {"detail": "An advisor is handling this conversation. Please wait for their response."},
                status=status.HTTP_200_OK,
            )

        raw_message = request.data.get("message", "")
        if not self._validate_and_sanitize_input(raw_message):
            return Response({"detail": "Invalid message"}, status=status.HTTP_400_BAD_REQUEST)

        sanitized_message = self._sanitize_message(raw_message)
        if not sanitized_message:
            return Response({"detail": "Empty message"}, status=status.HTTP_400_BAD_REQUEST)

        opening_message = _opening_user_message(conversation, already_saved=False)
        if not opening_message:
            blocked = _mr_caluu_token_block(request.user)
            if blocked is not None:
                return blocked

        # Save user message (short transaction)
        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                role="user",
                content=sanitized_message
            )

        def event_stream():
            full_text = ""
            quick = False
            metadata = {}
            learning_capture_done = False
            response_complete = False
            billable_reply = False

            def run_learning_capture(reason):
                """Record the knowledge gap. Runs once, the moment the model finishes.

                Fires on the ``meta`` event, which the orchestrator emits as soon as
                the model is done, so the gap is captured even if the browser hangs
                up before the stream is drained. The post-loop call covers streams
                that complete without a ``meta`` event.
                """
                nonlocal learning_capture_done
                if learning_capture_done:
                    return
                learning_capture_done = True
                if not full_text.strip():
                    logger.info(
                        f"[knowledge-gap] skip: no model answer to evaluate "
                        f"(trigger={reason}, '{sanitized_message[:50]}')"
                    )
                    return
                try:
                    from .learning import capture_knowledge_suggestion
                    capture_knowledge_suggestion(
                        query=sanitized_message,
                        response=full_text,
                        conversation=conversation,
                        user=request.user,
                        intent_info=intents,
                        search_results=search_results,
                        rag_context=rag_context,
                        source="send_message_stream",
                    )
                except Exception as e:
                    logger.error(
                        f"Knowledge suggestion capture failed in stream "
                        f"for user {request.user.id}: {e}"
                    )

            try:
                enhanced_service = get_enhanced_service()
                vector_service = get_vector_service()

                # Quick response path — FREE, no token charge
                message_count = conversation.messages.count()
                quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)
                if quick_type:
                    quick_text = enhanced_service.get_quick_response(quick_type, request.user)
                    if quick_text:
                        quick = True
                        full_text = quick_text
                        response_complete = True
                        learning_capture_done = True
                        yield f"data: {json.dumps({'type': 'text', 'content': quick_text})}\n\n"
                        with transaction.atomic():
                            assistant_msg = Message.objects.create(
                                conversation=conversation,
                                role="assistant",
                                content=quick_text,
                                tokens_used=0,
                                cost_tsh=0.0,
                            )
                            conversation.save(update_fields=["updated_at"])
                        logger.info(
                            f"[knowledge-gap] skip: quick response, no answer evaluated "
                            f"(user {request.user.id}, '{sanitized_message[:50]}')"
                        )
                        yield f"data: {json.dumps({'type': 'done', 'tokens_used': 0, 'cost_tsh': 0})}\n\n"
                        return

                # RAG search (no DB write inside)
                rag_context = ""
                navigation_context = ""
                intents = enhanced_service.classify_query_intent(sanitized_message)
                needs_kb = intents.get('needs_knowledge_base', True)
                primary_intent = intents.get('primary_intent', 'faq')
                search_results = None

                try:
                    university_id = None
                    if hasattr(request.user, 'student_profile') and request.user.student_profile:
                        university_id = request.user.student_profile.university_id
                    if needs_kb:
                        search_results = vector_service.search(
                            sanitized_message,
                            top_k=5 if intents.get('is_critical') else 3,
                            university_id=university_id,
                        )
                        if search_results:
                            rag_context = vector_service.format_for_prompt(
                                search_results,
                                max_chars=800 if intents.get('is_critical') else 600,
                            )
                        else:
                            logger.warning(f"⚠️ NO KNOWLEDGE BASE RESULTS in stream for '{sanitized_message}'")
                    if primary_intent == 'navigation':
                        nav_results = vector_service.search_navigation(sanitized_message, top_k=3)
                        if nav_results:
                            nav_lines = []
                            for nav in nav_results:
                                nav_lines.append(f"- {nav['name']}: {nav['description']} [LINK:{nav['route']}]")
                            navigation_context = "\n".join(nav_lines)

                    # Entity-specific searches (articles, opportunities, calendar events)
                    if primary_intent == 'articles':
                        article_context = enhanced_service.search_articles(sanitized_message, university_id)
                        if article_context:
                            rag_context += f"\n\nRELEVANT ARTICLES:\n{article_context}"

                    elif primary_intent == 'opportunities':
                        opp_context = enhanced_service.search_opportunities(sanitized_message, university_id)
                        if opp_context:
                            rag_context += f"\n\nRELEVANT OPPORTUNITIES:\n{opp_context}"

                    elif primary_intent == 'calendar_events':
                        calendar_context = enhanced_service.search_calendar_events(sanitized_message, university_id)
                        if calendar_context:
                            rag_context += f"\n\nRELEVANT CALENDAR EVENTS:\n{calendar_context}"
                except Exception as e:
                    logger.warning(f"RAG search failed in stream: {e}")

                # Native streaming — chunks arrive as LLM generates them
                for event in enhanced_service.get_enhanced_response_streaming(
                    sanitized_message,
                    request.user,
                    conversation,
                    rag_context,
                    navigation_context,
                    intent_info=intents,
                ):
                    if event["type"] == "text":
                        chunk = event["content"]
                        full_text += chunk
                        yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                    elif event["type"] == "meta":
                        metadata = {
                            'tokens_used': event['tokens_used'],
                            'cost_tsh': event['cost_tsh'],
                        }
                        full_text = event['reply']  # canonical cleaned text
                        billable_reply = bool(event.get("billable"))
                        response_complete = billable_reply
                        run_learning_capture("model_finished")

                # Add upcoming events alert naturally
                try:
                    upcoming_alert = enhanced_service.get_upcoming_events_alert(request.user)
                    if upcoming_alert:
                        full_text = f"{full_text}\n\n{upcoming_alert}"
                except Exception as e:
                    logger.debug(f"Failed to add upcoming events alert in stream: {e}")

                # Save message (short transaction)
                with transaction.atomic():
                    assistant_msg = Message.objects.create(
                        conversation=conversation,
                        role="assistant",
                        content=full_text,
                        tokens_used=metadata.get('tokens_used', 0),
                        cost_tsh=metadata.get('cost_tsh', 0.0),
                    )

                    # Same titling rule as the non-streaming path: name the
                    # conversation after its first substantive message.
                    updates = ["updated_at"]
                    if not conversation.title or conversation.title == "New Conversation":
                        derived = enhanced_service.summarize_conversation_title(
                            sanitized_message, full_text
                        )
                        if derived:
                            conversation.title = derived
                            updates.append("title")
                    conversation.save(update_fields=updates)

                # Memory updates (best-effort)
                try:
                    # Reconstruct a minimal EnhancedResponse for memory update
                    from .enhanced_service import EnhancedResponse
                    mem_response = EnhancedResponse(
                        text=full_text,
                        tokens_used=metadata.get('tokens_used', 0),
                        input_tokens=0,
                        output_tokens=metadata.get('tokens_used', 0),
                        cost_tsh=metadata.get('cost_tsh', 0.0),
                        summary=conversation.summary or "",
                        personality_notes=None,
                        instructions=None,
                    )
                    enhanced_service.update_memory(request.user, conversation, mem_response)
                except Exception as e:
                    logger.error(f"Memory update failed in stream: {e}")

                # LEARNING PIPELINE (Phase 5): capture knowledge gaps for staff review.
                try:
                    from .models import KnowledgeSuggestion, ConversationAnalytics

                    ask_is_question = bool(re.search(r'[?؟]', sanitized_message)) or bool(
                        re.search(r'\b(who|what|when|where|why|how|can|could|should|is|are|do|does)\b',
                                  sanitized_message.lower())
                    )
                    hedge_phrases = [
                        "i don't know", "i'm not sure", "i am not sure", "not certain",
                        "i couldn't find", "i can't find", "i cannot find", "no information",
                        "don't have information", "not in the knowledge base", "i can't answer",
                        "i don't have that", "i don't have access to", "unavailable",
                        "i'm unable to", "i am unable to", "i lack", "missing", "absent",
                        "not available", "not provided", "no data", "no details",
                        "i don't have details", "i don't have the details", "unclear",
                        "uncertain", "unsure", "ambiguous", "not specified", "not stated",
                        "i don't have that information", "i don't have that info",
                        "i don't have access to that", "i don't have the answer",
                        "i don't have the answer to that", "i don't know that",
                        "i don't know about that", "i'm not aware of", "i am not aware of",
                        "i don't have any information on", "i don't have any info on",
                        "there's no information", "there is no information", "there's no info",
                        "there is no info", "i cannot provide", "i can't provide",
                        "i'm not able to provide", "i am not able to provide",
                        "not mentioned", "not documented", "not recorded", "not listed",
                        "i don't see", "i can't see", "i cannot see", "i don't have record",
                        "i don't have records", "no record", "no records", "not found",
                        "i couldn't locate", "i can't locate", "i cannot locate",
                        "i don't have knowledge of", "i lack knowledge of", "unknown",
                        "i don't have clarity on", "i lack clarity on", "i'm unclear about",
                        "i am unclear about", "i don't have specifics", "i lack specifics",
                        "i don't have the specifics", "i lack the specifics", "i don't have context",
                        "i lack context", "i don't have the context", "i lack the context",
                        "i don't have that detail", "i lack that detail", "i don't have those details",
                        "i lack those details", "i don't have that data", "i lack that data",
                        "i don't have those data", "i lack those data", "i don't have that fact",
                        "i lack that fact", "i don't have those facts", "i lack those facts"
                    ]
                    low_confidence = any(p in full_text.lower() for p in hedge_phrases)

                    kb_miss = bool(needs_kb) and not rag_context
                    trigger = None
                    if ask_is_question and (kb_miss or low_confidence):
                        trigger = 'no_kb_result' if kb_miss else 'low_confidence'
                        import hashlib
                        query_hash = hashlib.sha256(
                            sanitized_message.lower().strip().encode()
                        ).hexdigest()
                        KnowledgeSuggestion.objects.get_or_create(
                            query_hash=query_hash,
                            defaults=dict(
                                query_text=sanitized_message,
                                response_text=full_text,
                                trigger=trigger,
                                confidence_score=0.0 if kb_miss else 0.3,
                                conversation=conversation,
                                user=request.user,
                            ),
                        )

                    if kb_miss or low_confidence:
                        g_analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=conversation)
                        gaps = list(g_analytics.knowledge_gaps or [])
                        gap_entry = {
                            'query': sanitized_message[:200],
                            'reason': trigger,
                            'at': timezone.now().isoformat(),
                        }
                        if not any(g.get('query', '') == gap_entry['query'] for g in gaps):
                            gaps.append(gap_entry)
                            g_analytics.knowledge_gaps = gaps[-20:]
                            g_analytics.save(update_fields=['knowledge_gaps'])
                except Exception as e:
                    logger.debug(f"Learning capture skipped in stream: {e}")

                if billable_reply:
                    _charge_mr_caluu(
                        request.user,
                        assistant_msg,
                        full_text,
                        _opening_user_message(conversation, already_saved=True),
                    )

                yield f"data: {json.dumps({'type': 'done', 'reply': full_text, **metadata})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error for user {request.user.id}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'detail': str(e)[:300]})}\n\n"
            finally:
                if not learning_capture_done:
                    # SSE is pull-based: a client that hangs up after the last text
                    # chunk never causes the ``meta`` event above to be read, so the
                    # capture would be lost even though the model did finish. The
                    # trigger is derived from knowledge-base coverage (exact) rather
                    # than from the answer text, so a partial ``full_text`` here only
                    # costs staff a truncated quote, never a wrong trigger.
                    if not response_complete:
                        logger.warning(
                            f"[knowledge-gap] stream closed before the model finished "
                            f"(user {request.user.id}, {len(full_text)} chars received, "
                            f"'{sanitized_message[:50]}') — recording gap from a "
                            f"possibly partial answer"
                        )
                    run_learning_capture("stream_closed_early")

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request, pk=None):
        conversation = self.get_object()
        data = MessageSerializer(conversation.messages.order_by("timestamp"), many=True).data
        return Response(data)

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        convo = Conversation.objects.filter(user=request.user, is_active=True).order_by("-updated_at").first()
        if not convo:
            convo = Conversation.objects.create(user=request.user, title="New Conversation", is_active=True)

        # This endpoint is polled on every chat open, so it used to serialise the
        # entire message history every time -- 27KB for a 65-message thread and
        # growing without bound. Send the most recent page plus a total count so
        # the UI can still show "load earlier".
        messages = list(
            convo.messages.order_by("-timestamp")[:ACTIVE_MESSAGE_PAGE]
        )[::-1]
        return Response({
            "id": convo.id,
            "title": convo.title,
            "is_active": convo.is_active,
            "created_at": convo.created_at,
            "updated_at": convo.updated_at,
            "total_tokens": convo.total_tokens,
            "total_input_tokens": convo.total_input_tokens,
            "total_output_tokens": convo.total_output_tokens,
            "total_cost_tsh": convo.total_cost_tsh,
            "messages": MessageSerializer(messages, many=True).data,
            "total_messages": convo.messages.count(),
            "messages_truncated": convo.messages.count() > len(messages),
        })

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        convo = self.get_object()
        convo.is_active = False
        convo.save()
        return Response({"status": "archived"})

    @action(detail=True, methods=["post"], url_path="upload_document")
    def upload_document(self, request, pk=None):
        """Upload a document to the conversation for RAG context (Phase 8)."""
        conversation = self.get_object()
        file = request.FILES.get('file')

        if not file:
            return Response({"detail": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        from .models import ConversationDocument

        ext = file.name.split('.')[-1].lower() if '.' in file.name else 'txt'
        type_map = {'pdf': 'pdf', 'docx': 'docx', 'txt': 'txt', 'md': 'txt',
                    'png': 'image', 'jpg': 'image', 'jpeg': 'image'}
        attachment_type = type_map.get(ext, 'txt')

        doc = ConversationDocument.objects.create(
            conversation=conversation,
            file=file,
            filename=file.name,
            attachment_type=attachment_type,
        )

        # Basic text extraction (txt only for now; PDF/DOCX left as extension point)
        try:
            if attachment_type == 'txt':
                content = file.read().decode('utf-8', errors='ignore')
                doc.extracted_text = content
                doc.is_processed = True
                doc.save()
        except Exception as e:
            logger.error(f"Text extraction failed for doc {doc.id}: {e}")

        return Response({
            'id': str(doc.id),
            'filename': doc.filename,
            'type': doc.attachment_type,
            'is_processed': doc.is_processed,
        }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def suggestions_list(request):
    """List knowledge suggestions for staff review (Phase 5)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    from .models import KnowledgeSuggestion

    status_filter = request.query_params.get('status', 'pending')
    suggestions = KnowledgeSuggestion.objects.filter(status=status_filter).select_related('user', 'reviewed_by')

    try:
        limit = min(max(int(request.query_params.get('limit', 50)), 1), 200)
    except (TypeError, ValueError):
        limit = 50

    serializer = KnowledgeSuggestionSerializer(
        suggestions.order_by('-occurrence_count', '-last_seen_at')[:limit], many=True
    )
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_suggestion(request, pk):
    """Approve a suggestion — creates a KnowledgeDocument from it (Phase 5)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    from .models import KnowledgeSuggestion, KnowledgeDocument

    try:
        suggestion = KnowledgeSuggestion.objects.get(id=pk)
    except KnowledgeSuggestion.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if suggestion.status != 'pending':
        return Response({"detail": "Suggestion has already been reviewed"}, status=status.HTTP_400_BAD_REQUEST)

    suggestion.status = 'approved'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()

    title = request.data.get('title') or suggestion.query_text[:100]
    content = request.data.get('content', suggestion.response_text)
    category = request.data.get('category', 'faq')
    university_id = request.data.get('university_id')
    # An approved suggestion becomes real, searchable knowledge immediately.
    # Its authority is whatever the reviewer declares -- a student-leader
    # clarification must stay labelled as such once it is in the knowledge base.
    source_level = request.data.get('source_level', 'general')
    if source_level not in dict(KnowledgeDocument.SOURCE_LEVELS):
        source_level = 'general'
    source_attribution = request.data.get('source_attribution', '') or ''

    doc = KnowledgeDocument.objects.create(
        title=title,
        content=content,
        category=category,
        university_id=university_id or None,
        source_level=source_level,
        source_attribution=source_attribution,
        is_active=True,
    )
    suggestion.source_level = source_level
    suggestion.save(update_fields=["source_level"])
    logger.info(
        f"Knowledge document created from suggestion {suggestion.id}: "
        f"{doc.title} (source_level={source_level})"
    )

    # Precompute embedding so the approved doc is immediately searchable
    # (cheap, lazy; no-op if the semantic model is unavailable).
    try:
        from .vector_service import VectorSearchService
        service = get_vector_service()
        if service.model is not None:
            service._store_embedding(doc, f"{doc.title}. {doc.content}")
            service.build_index(university_id=university_id)
    except Exception as e:
        logger.debug(f"Embedding index refresh skipped after approve: {e}")

    serializer = KnowledgeSuggestionSerializer(suggestion)
    return Response({
        'status': 'approved',
        'document_id': str(doc.id),
        'suggestion': serializer.data
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_suggestion(request, pk):
    """Reject a suggestion (Phase 5)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    from .models import KnowledgeSuggestion

    try:
        suggestion = KnowledgeSuggestion.objects.get(id=pk)
    except KnowledgeSuggestion.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if suggestion.status != 'pending':
        return Response({"detail": "Suggestion has already been reviewed"}, status=status.HTTP_400_BAD_REQUEST)

    suggestion.status = 'rejected'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()

    logger.info(f"KnowledgeSuggestion {suggestion.id} rejected by {request.user.display_name}")

    serializer = KnowledgeSuggestionSerializer(suggestion)
    return Response({
        'status': 'rejected',
        'suggestion': serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def knowledge_gaps(request):
    """Aggregated knowledge gaps for the staff review dashboard (Phase 5)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    from .models import KnowledgeSuggestion
    from django.db.models import Count, Q

    # Group pending suggestions by trigger (what kind of gap they represent)
    by_trigger = dict(
        KnowledgeSuggestion.objects.filter(status='pending')
        .values('trigger').annotate(count=Count('id')).values_list('trigger', 'count')
    )

    # Recently repeated, unanswered questions (helps spot trending gaps)
    trending = list(
        KnowledgeSuggestion.objects.filter(
            status='pending', trigger='no_kb_result'
        ).order_by('-created_at')[:15].values(
            'id', 'query_text', 'created_at'
        )
    )

    return Response({
        'by_trigger': by_trigger,
        'pending_total': KnowledgeSuggestion.objects.filter(status='pending').count(),
        'trending': trending,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_conversation(request, pk):
    """Admin enters co-pilot mode on a conversation (Phase 6)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        conversation = Conversation.objects.get(id=pk)
    except Conversation.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    conversation.mode = 'admin_copilot'
    conversation.save(update_fields=['mode'])

    # Notice to the student (simple safe default)
    Message.objects.create(
        conversation=conversation,
        role='assistant',
        content="an advisor has joined this conversation and is here to help! 😊",
        tokens_used=0,
        cost_tsh=0.0,
    )

    return Response({'status': 'admin_copilot', 'mode': conversation.mode})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_conversation(request, pk):
    """Admin leaves co-pilot mode; bot resumes (Phase 6)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        conversation = Conversation.objects.get(id=pk)
    except Conversation.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    conversation.mode = 'bot'
    conversation.save(update_fields=['mode'])

    Message.objects.create(
        conversation=conversation,
        role='assistant',
        content="Thanks for chatting! Mr Caluu is back to help. 🤖",
        tokens_used=0,
        cost_tsh=0.0,
    )

    return Response({'status': 'bot', 'mode': conversation.mode})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def draft_reply(request, pk):
    """Generate a draft reply for admin review (co-pilot, Phase 6).

    The draft is shown only to the admin — never sent to the student.
    Draft generation is platform-side / unmetered (not student-charged).
    """
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        conversation = Conversation.objects.get(id=pk)
    except Conversation.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    last_user_msg = conversation.messages.filter(role='user').order_by('-timestamp').first()
    if not last_user_msg:
        return Response({"detail": "No user message to reply to"}, status=status.HTTP_400_BAD_REQUEST)

    enhanced_service = get_enhanced_service()
    vector_service = get_vector_service()

    rag_context = ""
    try:
        search_results = vector_service.search(last_user_msg.content, top_k=3)
        if search_results:
            rag_context = vector_service.format_for_prompt(search_results)
    except Exception:
        pass

    try:
        ai_response = enhanced_service.get_enhanced_response(
            last_user_msg.content,
            conversation.user,
            conversation,
            rag_context,
        )
    except Exception as e:
        logger.error(f"Draft generation failed: {e}")
        return Response(
            {"detail": "Draft generation failed. Please write the reply manually."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'draft': ai_response.text,
        'tokens_used': ai_response.tokens_used,
        'cost_tsh': ai_response.cost_tsh,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_send(request, pk):
    """Admin sends a message — bypasses bot pipeline, no token charge (Phase 6)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        conversation = Conversation.objects.get(id=pk)
    except Conversation.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    message_text = request.data.get('message', '').strip()
    if not message_text:
        return Response({"detail": "Message required"}, status=status.HTTP_400_BAD_REQUEST)

    # Save admin message as assistant (student sees it as from Mr Caluu)
    with transaction.atomic():
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=message_text,
            tokens_used=0,
            cost_tsh=0.0,
        )
        conversation.save(update_fields=['updated_at'])

    # NO token consumption — admin-authored messages never deduct student tokens.
    # NO automatic bot pipeline re-trigger for this turn.

    return Response({'status': 'sent'})


@api_view(["POST"]) 
@permission_classes([IsAuthenticated])
def quick_chat(request):
    """Quick chat endpoint without conversation persistence"""
    message = request.data.get("message", "").strip()
    if not message:
        return Response({"detail": "message is required"}, status=status.HTTP_400_BAD_REQUEST)

    service = get_enhanced_service()
    
    # Only use quick response for very simple greeting
    lowered = message.lower()
    if len(lowered) <= 15 and re.match(r"^(hi|hello|hey)\b", lowered):
        quick_response = service.get_quick_response("greeting", request.user)
        if quick_response:
            return Response({"reply": quick_response, "tokens_used": 0, "cost_tsh": 0.0})

    # Otherwise, use AI (but without conversation context)
    try:
        # Create temporary conversation context
        from .models import Conversation
        temp_convo = Conversation.objects.filter(user=request.user, title="Quick Chat").first()
        if not temp_convo:
            temp_convo = Conversation.objects.create(user=request.user, title="Quick Chat", is_active=False)
        
        response = service.get_enhanced_response(message, request.user, temp_convo, "")
        return Response({
            "reply": response.text,
            "tokens_used": response.tokens_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_tsh": response.cost_tsh,
        })
    except Exception as e:
        # Enhanced error handling for quick chat
        error_type = type(e).__name__
        error_msg = str(e).lower()
        logger.error(f"Quick chat error for user {request.user.id}: {error_type} - {error_msg}")

        # Provide specific error messages based on error type
        if "authentication" in error_msg or "unauthorized" in error_msg or "invalid" in error_msg:
            reply = "I'm having trouble with my API access. Please check if the AI service key is properly configured."
        elif "rate limit" in error_msg or "quota" in error_msg or "usage" in error_msg:
            reply = "I'm currently at my usage limit. Please try again in a few minutes."
        elif "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
            reply = "I'm having trouble connecting to the AI service. Please check your internet connection."
        elif "server" in error_msg or "internal" in error_msg or "500" in error_msg:
            reply = "The AI service is temporarily unavailable. Please try again in a moment."
        else:
            reply = "AI is temporarily unavailable. Please try again in a moment."

        return Response({
            "reply": reply,
            "tokens_used": 0,
            "cost_tsh": 0.0
        }, status=status.HTTP_200_OK)


@api_view(["GET"]) 
@permission_classes([IsAuthenticated])
def chat_stats(request):
    """Get chat statistics for the current user"""
    qs = Conversation.objects.filter(user=request.user)
    
    total_conversations = qs.count()
    active_conversations = qs.filter(is_active=True).count()
    total_messages = Message.objects.filter(conversation__user=request.user).count()
    total_tokens = Message.objects.filter(
        conversation__user=request.user,
        role="assistant"
    ).aggregate(total=Sum("tokens_used"))["total"] or 0
    total_cost = Message.objects.filter(
        conversation__user=request.user,
        role="assistant"
    ).aggregate(total=Sum("cost_tsh"))["total"] or 0.0

    return Response({
        "total_conversations": total_conversations,
        "active_conversations": active_conversations,
        "total_messages": total_messages,
        "total_tokens_used": total_tokens,
        "total_cost_tsh": round(total_cost, 2),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def personality_profile(request):
    """Get the user's personality profile and preferences"""
    chat_history, _ = ChatHistory.objects.get_or_create(user=request.user)
    serializer = ChatHistorySerializer(chat_history)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_feedback(request):
    """Submit feedback on a chatbot response"""
    from .models import Feedback, Message, Conversation
    
    message_id = request.data.get("message_id")
    rating = request.data.get("rating")
    comment = request.data.get("comment", "")
    query = request.data.get("query", "")
    response_text = request.data.get("response", "")
    
    if not message_id or not rating:
        return Response(
            {"detail": "message_id and rating are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if rating not in [1, 2, 3, 4, 5]:
        return Response(
            {"detail": "rating must be between 1 and 5"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        message = Message.objects.get(id=message_id, conversation__user=request.user)
        
        feedback = Feedback.objects.create(
            user=request.user,
            conversation=message.conversation,
            message=message,
            rating=rating,
            comment=comment,
            query=query or message.conversation.messages.filter(role="user").order_by("-timestamp").first().content if message.conversation.messages.filter(role="user").exists() else "",
            response=response_text or message.content
        )
        
        # Update analytics
        from .models import ConversationAnalytics
        analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=message.conversation)
        analytics.update_metrics(rating=rating)

        # LEARNING PIPELINE (Phase 5): capture negative ratings for staff review
        if int(rating) <= 2:
            from .learning import capture_negative_feedback
            preceding = (
                message.conversation.messages.filter(role="user")
                .order_by("-timestamp").first()
            )
            capture_negative_feedback(
                query=query or (preceding.content if preceding else ""),
                response=response_text or message.content,
                conversation=message.conversation,
                user=request.user,
                rating=int(rating),
            )

        logger.info(f"Feedback submitted: {rating}/5 by user {request.user.id} for message {message_id}")
        
        return Response({
            "message": "Feedback submitted successfully",
            "feedback_id": str(feedback.id)
        }, status=status.HTTP_201_CREATED)
        
    except Message.DoesNotExist:
        return Response(
            {"detail": "Message not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return Response(
            {"detail": f"Error submitting feedback: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_dashboard(request):
    """Get analytics dashboard data for admin/staff"""
    from .models import ConversationAnalytics, Feedback, KnowledgeDocument
    from django.db.models import Avg, Count, Q
    
    # Check if user is staff/admin (you may want to add proper permission checks)
    if not request.user.is_staff:
        return Response(
            {"detail": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Overall statistics
    total_conversations = Conversation.objects.count()
    total_messages = Message.objects.count()
    total_feedback = Feedback.objects.count()
    avg_rating = Feedback.objects.aggregate(avg=Avg('rating'))['avg'] or 0.0
    
    # Knowledge base statistics
    kb_stats = {
        'total_documents': KnowledgeDocument.objects.count(),
        'active_documents': KnowledgeDocument.objects.filter(is_active=True).count(),
        'by_category': dict(KnowledgeDocument.objects.values('category').annotate(count=Count('id')).values_list('category', 'count')),
        'most_used': list(KnowledgeDocument.objects.order_by('-usage_count')[:10].values('title', 'category', 'usage_count'))
    }
    
    # Query intent distribution
    intent_distribution = dict(
        ConversationAnalytics.objects.exclude(query_intent='').values('query_intent')
        .annotate(count=Count('id')).values_list('query_intent', 'count')
    )
    
    # Recent low-rated feedback
    low_rated_feedback = Feedback.objects.filter(rating__lte=2).order_by('-created_at')[:10].values(
        'id', 'rating', 'query', 'comment', 'created_at', 'user__display_name'
    )
    
    # Performance metrics
    performance = {
        'avg_response_time': ConversationAnalytics.objects.aggregate(avg=Avg('avg_response_time'))['avg'] or 0.0,
        'total_api_calls': ConversationAnalytics.objects.aggregate(total=Sum('total_api_calls'))['total'] or 0,
        'total_cache_hits': ConversationAnalytics.objects.aggregate(total=Sum('total_cache_hits'))['total'] or 0,
    }
    
    cache_hit_rate = 0.0
    if performance['total_api_calls'] + performance['total_cache_hits'] > 0:
        cache_hit_rate = (performance['total_cache_hits'] / 
                         (performance['total_api_calls'] + performance['total_cache_hits'])) * 100
    
    return Response({
        'overview': {
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'total_feedback': total_feedback,
            'average_rating': round(avg_rating, 2),
        },
        'knowledge_base': kb_stats,
        'query_intents': intent_distribution,
        'performance': {
            **performance,
            'cache_hit_rate': round(cache_hit_rate, 2)
        },
        'low_rated_feedback': list(low_rated_feedback),
    }, status=status.HTTP_200_OK)
