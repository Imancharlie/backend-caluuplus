from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chatbot'

    def ready(self):
        # Import signals so RAG cache auto-invalidates on content change (Phase 4)
        import chatbot.signals  # noqa: F401
