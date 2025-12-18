from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChatbotViewSet, quick_chat, chat_stats, personality_profile,
    submit_feedback, analytics_dashboard
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
]



