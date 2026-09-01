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
from .serializers import ConversationSerializer, MessageSerializer, ChatHistorySerializer
from .enhanced_service import EnhancedClaudeService
from .vector_service import VectorSearchService
from .anthropic_service import AnthropicService

logger = logging.getLogger(__name__)

# Alias for clarity - use 're' throughout the file
re = regex_module


class ChatbotViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

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

        # TOKEN SAFETY (pre-check): reject immediately if balance is zero, before any LLM call.
        # A full LLM call later may push the balance slightly negative (by ~1 message cost),
        # which is the grace per Phase 6. The next message will be rejected here.
        try:
            from tokens.services import has_balance_for
            if not has_balance_for(request.user, rule_key="MR_CALUU_MESSAGE"):
                return Response(
                    {"detail": "You've run out of tokens! Top up to keep chatting with Mr Caluu. 🪙"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass  # If the check fails (rule missing, wallet issue), let it proceed.

        # Save user message (short transaction, no LLM)
        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                role="user",
                content=sanitized_message
            )

        # Initialize services (reused across quick + AI paths)
        enhanced_service = EnhancedClaudeService()
        vector_service = VectorSearchService()

        quick = None
        ai_response = None
        assistant_msg = None
        intent_info = None

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
            # ---- LLM path: ALL RAG + LLM work happens OUTSIDE any transaction ----
            logger.info(f"Generating AI response for user {request.user.id}")

            intent_info = enhanced_service.classify_query_intent(sanitized_message)
            needs_kb = intent_info.get('needs_knowledge_base', True)
            primary_intent = intent_info.get('primary_intent', 'faq')

            rag_context = ""
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
            except Exception as e:
                logger.warning(f"RAG/navigation search failed for user {request.user.id}: {str(e)}")

            # LLM call (no DB write inside)
            ai_response = enhanced_service.get_enhanced_response(
                sanitized_message,
                request.user,
                conversation,
                rag_context,
                navigation_context
            )

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
                conversation.save(update_fields=["updated_at"])

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

        # TOKEN SAFETY (finalize): only charge for actual LLM calls.
        # Quick responses and cached hits are FREE — they never deduct tokens.
        if not quick:
            try:
                from tokens import services as token_service
                token_service.consume(
                    request.user,
                    "MR_CALUU_MESSAGE",
                    reference_key=f"mrcaluu:{assistant_msg.id}" if assistant_msg else None,
                    description="Mr Caluu message",
                    initiated_by="chatbot",
                )
            except Exception as e:
                logger.warning(f"Mr Caluu token consumption skipped for user {request.user.id}: {str(e)}")

        # Capture learning suggestions (Phase 5)
        try:
            from .models import KnowledgeSuggestion
            if intent_info is not None:
                needs_kb = intent_info.get('needs_knowledge_base', True)
            else:
                needs_kb = False
            if needs_kb and not rag_context and ai_response is not None:
                KnowledgeSuggestion.objects.create(
                    query_text=sanitized_message,
                    response_text=ai_response.text,
                    trigger='no_kb_result',
                    confidence_score=0.0,
                    conversation=conversation,
                    user=request.user,
                )
        except Exception as e:
            logger.debug(f"Knowledge suggestion capture skipped: {e}")

        serializer = ConversationSerializer(conversation)
        total_time = time.time() - start_time
        logger.info(f"Message processing completed for user {request.user.id} in {total_time:.2f}s")

        return Response(serializer.data)

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

        # TOKEN SAFETY (pre-check): reject immediately before any LLM work.
        try:
            from tokens.services import has_balance_for
            if not has_balance_for(request.user, rule_key="MR_CALUU_MESSAGE"):
                return Response(
                    {"detail": "You've run out of tokens! Top up to keep chatting with Mr Caluu. 🪙"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

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

            try:
                enhanced_service = EnhancedClaudeService()
                vector_service = VectorSearchService()

                # Quick response path — FREE, no token charge
                message_count = conversation.messages.count()
                quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)
                if quick_type:
                    quick_text = enhanced_service.get_quick_response(quick_type, request.user)
                    if quick_text:
                        quick = True
                        full_text = quick_text
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
                        yield f"data: {json.dumps({'type': 'done', 'tokens_used': 0, 'cost_tsh': 0})}\n\n"
                        return

                # RAG search (no DB write inside)
                rag_context = ""
                navigation_context = ""
                intents = enhanced_service.classify_query_intent(sanitized_message)
                needs_kb = intents.get('needs_knowledge_base', True)
                primary_intent = intents.get('primary_intent', 'faq')

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
                    if primary_intent == 'navigation':
                        nav_results = vector_service.search_navigation(sanitized_message, top_k=3)
                        if nav_results:
                            nav_lines = []
                            for nav in nav_results:
                                nav_lines.append(f"- {nav['name']}: {nav['description']} [LINK:{nav['route']}]")
                            navigation_context = "\n".join(nav_lines)
                except Exception as e:
                    logger.warning(f"RAG search failed in stream: {e}")

                # LLM call (outside any transaction)
                ai_response = enhanced_service.get_enhanced_response(
                    sanitized_message,
                    request.user,
                    conversation,
                    rag_context,
                    navigation_context,
                )

                full_text = ai_response.text

                # Emit text in chunks for a streaming feel
                chunk_size = 24
                for i in range(0, len(full_text), chunk_size):
                    chunk = full_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                    time.sleep(0.015)

                metadata = {
                    'tokens_used': ai_response.tokens_used,
                    'cost_tsh': ai_response.cost_tsh,
                }

                # Save message (short transaction)
                with transaction.atomic():
                    assistant_msg = Message.objects.create(
                        conversation=conversation,
                        role="assistant",
                        content=full_text,
                        tokens_used=ai_response.tokens_used,
                        cost_tsh=ai_response.cost_tsh,
                    )
                    conversation.save(update_fields=["updated_at"])

                # Memory updates (best-effort)
                try:
                    enhanced_service.update_memory(request.user, conversation, ai_response)
                except Exception as e:
                    logger.error(f"Memory update failed in stream: {e}")

                # LEARNING PIPELINE (Phase 5): capture knowledge gaps for staff review.
                # Never fails the user's turn — always best-effort.
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

                    # Populate the (previously unused) knowledge_gaps metric.
                    if kb_miss or low_confidence:
                        g_analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=conversation)
                        gaps = list(g_analytics.knowledge_gaps or [])
                        gap_entry = {
                            'query': sanitized_message[:200],
                            'reason': trigger if 'trigger' in locals() else ('no_kb_result' if kb_miss else 'low_confidence'),
                            'at': timezone.now().isoformat(),
                        }
                        if not any(g.get('query', '') == gap_entry['query'] for g in gaps):
                            gaps.append(gap_entry)
                            g_analytics.knowledge_gaps = gaps[-20:]
                            g_analytics.save(update_fields=['knowledge_gaps'])
                except Exception as e:
                    logger.debug(f"Learning capture skipped in stream: {e}")

                # TOKEN SAFETY (finalize): charge only real LLM turns
                try:
                    from tokens import services as token_service
                    token_service.consume(
                        request.user,
                        "MR_CALUU_MESSAGE",
                        reference_key=f"mrcaluu:{assistant_msg.id}",
                        description="Mr Caluu message",
                        initiated_by="chatbot",
                    )
                except Exception as e:
                    logger.warning(f"Token consumption skipped in stream: {e}")

                yield f"data: {json.dumps({'type': 'done', **metadata})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error for user {request.user.id}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'detail': str(e)[:300]})}\n\n"

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
        return Response(ConversationSerializer(convo).data)

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
    suggestions = KnowledgeSuggestion.objects.filter(status=status_filter)

    data = [{
        'id': str(s.id),
        'query_text': s.query_text,
        'response_text': s.response_text,
        'trigger': s.trigger,
        'confidence_score': s.confidence_score,
        'status': s.status,
        'created_at': s.created_at.isoformat(),
    } for s in suggestions[:50]]

    return Response(data)


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

    suggestion.status = 'approved'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()

    title = request.data.get('title', suggestion.query_text[:100])
    content = request.data.get('content', suggestion.response_text)
    category = request.data.get('category', 'faq')
    university_id = request.data.get('university_id')

    doc = KnowledgeDocument.objects.create(
        title=title,
        content=content,
        category=category,
        university_id=university_id or None,
        is_active=True,
    )
    logger.info(f"Knowledge document created from suggestion {suggestion.id}: {doc.title}")

    # Precompute embedding so the approved doc is immediately searchable
    # (cheap, lazy; no-op if the semantic model is unavailable).
    try:
        from .vector_service import VectorSearchService
        service = VectorSearchService()
        if service.model is not None:
            service._store_embedding(doc, f"{doc.title}. {doc.content}")
            service.build_index(university_id=university_id)
    except Exception as e:
        logger.debug(f"Embedding index refresh skipped after approve: {e}")

    return Response({'status': 'approved', 'document_id': str(doc.id)})


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

    suggestion.status = 'rejected'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()

    return Response({'status': 'rejected'})


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

    enhanced_service = EnhancedClaudeService()
    vector_service = VectorSearchService()

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

    service = EnhancedClaudeService()
    
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
            from .models import KnowledgeSuggestion
            KnowledgeSuggestion.objects.create(
                query_text=query or (message.conversation.messages.filter(role="user").order_by("-timestamp").first().content if message.conversation.messages.filter(role="user").exists() else ""),
                response_text=response_text or message.content,
                trigger='negative_rating',
                confidence_score=float(rating) / 5.0,
                conversation=message.conversation,
                user=request.user,
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
