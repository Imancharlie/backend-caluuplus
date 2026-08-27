from django.apps import AppConfig


class CaluuMapConfig(AppConfig):
    """AppConfig for the Caluu Map feature app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "caluu_map"
    verbose_name = "Caluu Map"

    def ready(self):
        # Wire up the synchronization change-log signals.
        from . import signals  # noqa: F401