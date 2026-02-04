from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onboarding"

    def ready(self):
        """Import signals when app is ready."""
        # Import signals to register them with Django
        import onboarding.signals  # noqa: F401
