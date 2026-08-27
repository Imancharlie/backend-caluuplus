import re as regex_module
import time
import logging
from django.db import transaction
from django.db.models import Sum, Avg, Count
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
        """Enhanced send_message with memory and RAG"""
        start_time = time.time()
        conversation = self.get_object()

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

        # Initialize variables
        quick = None
        ai_response = None
        assistant_msg = None

        # Retry logic for database operations
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    # Save user message
                    user_msg = Message.objects.create(
                        conversation=conversation,
                        role="user",
                        content=sanitized_message
                    )

                    # Initialize services
                    enhanced_service = EnhancedClaudeService()
                    vector_service = VectorSearchService()

                    # Smart response prioritization: Check if we can use quick response (saves tokens & cost)
                    message_count = conversation.messages.count()
                    quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)

                    if quick_type:
                        quick = enhanced_service.get_quick_response(quick_type, request.user)
                        logger.info(f"Using quick {quick_type} response for user {request.user.id} - saved ~200 tokens")

                    if quick:
                        logger.info(f"Using quick response for user {request.user.id}, type: {quick_type}")
                        # Quick response (no API call)
                        assistant_msg = Message.objects.create(
                            conversation=conversation,
                            role="assistant",
                            content=quick,
                            tokens_used=0,
                            cost_tsh=0.0
                        )

                    else:
                        # Use AI with RAG and intent classification
                        logger.info(f"Generating AI response for user {request.user.id}")
                        
                        # OPTIMIZATION: Do intent classification and RAG search in parallel where possible
                        # Classify query intent (lightweight operation)
                        intent_info = enhanced_service.classify_query_intent(sanitized_message)
                        needs_kb = intent_info.get('needs_knowledge_base', True)
                        primary_intent = intent_info.get('primary_intent', 'faq')
                        
                        # Get RAG context with university-specific knowledge
                        rag_context = ""
                        navigation_context = ""
                        
                        try:
                            # Get user's university if available (cache this lookup)
                            university_id = None
                            if hasattr(request.user, 'student_profile') and request.user.student_profile:
                                university_id = request.user.student_profile.university_id
                            
                            # OPTIMIZATION: Only search if knowledge base is needed
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
                                    logger.info(f"📚 KNOWLEDGE BASE USED")
                                    logger.info(f"   Found {len(search_results)} documents")
                                    logger.info(f"   Best relevance: {search_results[0].get('relevance', 0):.3f}")
                                    logger.info(f"   RAG context length: {len(rag_context)} chars")
                                    logger.info(f"   RAG preview: {rag_context[:150]}...")
                                else:
                                    logger.warning(f"⚠️ NO KNOWLEDGE BASE RESULTS")
                                    logger.warning(f"   Query: '{sanitized_message}'")
                                    logger.warning(f"   Intent: {primary_intent}")
                                    logger.warning(f"   Needs KB: {needs_kb}")
                            
                            # OPTIMIZATION: Only search navigation if intent is navigation
                            if primary_intent == 'navigation':
                                nav_results = vector_service.search_navigation(sanitized_message, top_k=3)
                                if nav_results:
                                    nav_lines = []
                                    for nav in nav_results:
                                        nav_lines.append(f"- {nav['name']}: {nav['description']} [LINK:{nav['route']}]")
                                    navigation_context = "\n".join(nav_lines)
                                    logger.info(f"Added {len(nav_results)} navigation results")
                        except Exception as e:
                            logger.warning(f"RAG/navigation search failed for user {request.user.id}: {str(e)}")
                            # Continue without RAG

                        # Get AI response
                        ai_response = enhanced_service.get_enhanced_response(
                            sanitized_message,
                            request.user,
                            conversation,
                            rag_context,
                            navigation_context
                        )
                        
                        # Update analytics
                        try:
                            from .models import ConversationAnalytics
                            analytics, _ = ConversationAnalytics.objects.get_or_create(conversation=conversation)
                            analytics.query_intent = primary_intent
                            analytics.update_metrics(api_call=True)
                            analytics.save()
                        except Exception as e:
                            logger.debug(f"Error updating analytics: {e}")

                        # Save assistant message
                        assistant_msg = Message.objects.create(
                            conversation=conversation,
                            role="assistant",
                            content=ai_response.text,
                            tokens_used=ai_response.tokens_used,
                            cost_tsh=ai_response.cost_tsh
                        )

                        logger.info(f"AI response saved for user {request.user.id}, tokens: {ai_response.tokens_used}, cost: {ai_response.cost_tsh} TSH")

                    # Update conversation timestamp
                    conversation.save()
                    
                    # Exit retry loop on success
                    break

            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Database transaction attempt {attempt + 1} failed for user {request.user.id}: {error_msg}")

                if attempt < max_retries - 1 and (
                    "database is locked" in error_msg or
                    "deadlock" in error_msg or
                    "lock" in error_msg
                ):
                    # Retry on database lock issues
                    wait_time = (2 ** attempt) * 0.1  # 0.1s, 0.2s, 0.4s
                    logger.info(f"Retrying database transaction in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Non-retryable error or final attempt
                    logger.error(f"Failed to save message for user {request.user.id}: {str(e)}")
                    return Response(
                        {"detail": f"Failed to process message: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

        # Update memory after main transaction (with error handling for locks)
        if ai_response is not None:
            try:
                # OPTIMIZATION: Reduced delay - memory update is less critical than response time
                time.sleep(0.005)  # Reduced from 0.01s
                enhanced_service.update_memory(request.user, conversation, ai_response)
                logger.info(f"Memory updated for user {request.user.id}")
            except Exception as e:
                logger.error(f"Memory update failed for user {request.user.id}: {e}")
                # Don't fail the entire request if memory update fails

        # Charge for the Mr Caluu interaction via the central token service
        # (purchased first, then earned). Best-effort so a low balance does not
        # block the user experience.
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

        serializer = ConversationSerializer(conversation)
        total_time = time.time() - start_time
        logger.info(f"Message processing completed for user {request.user.id} in {total_time:.2f}s")

        return Response(serializer.data)

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
