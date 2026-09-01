from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChatbotViewSet, quick_chat, chat_stats, personality_profile,
    submit_feedback, analytics_dashboard,
    suggestions_list, approve_suggestion, reject_suggestion, knowledge_gaps,
    join_conversation, leave_conversation, draft_reply, admin_send,
)


router = DefaultRouter()
router.register(r"conversations", ChatbotViewSet, basename="chatbot-conversation")

urlpatterns = [
    path("", include(router.urls)),
    path("quick/", quick_chat, name="chatbot-quick"),
    path("stats/", chat_stats, name="chatbot-stats"),
    path("profile/", personality_profile, name="chatbot-profile"),
    path("feedback/", submit_feedback, name="chatbot-feedback"),
    path("analytics/", analytics_dashboard, name="chatbot-analytics"),
    # Learning pipeline (Phase 5)
    path("suggestions/", suggestions_list, name="chatbot-suggestions"),
    path("suggestions/<uuid:pk>/approve/", approve_suggestion, name="chatbot-suggest-approve"),
    path("suggestions/<uuid:pk>/reject/", reject_suggestion, name="chatbot-suggest-reject"),
    path("gaps/", knowledge_gaps, name="chatbot-gaps"),
    # Admin co-pilot (Phase 6)
    path("conversations/<uuid:pk>/join/", join_conversation, name="chatbot-join"),
    path("conversations/<uuid:pk>/leave/", leave_conversation, name="chatbot-leave"),
    path("conversations/<uuid:pk>/draft/", draft_reply, name="chatbot-draft"),
    path("conversations/<uuid:pk>/admin-send/", admin_send, name="chatbot-admin-send"),
]
