"""Application configuration for the news app."""
from django.apps import AppConfig


class NewsConfig(AppConfig):
    """Configures the news app and registers its signal handlers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "news"

    def ready(self):
        """Import the signals module so its receivers are connected."""
        from . import signals  # noqa: F401
