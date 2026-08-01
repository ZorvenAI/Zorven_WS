from django.apps import AppConfig


class OnboardingSessionsConfig(AppConfig):
    """Configuration for the OIA session models.

    The label is **not** the default. Django derives an app label from the
    final path segment, which would be ``onboarding`` — already taken by the
    existing five-step wizard app at ``ai-brand-automator/onboarding/``. Two
    apps cannot share a label; Django refuses to start with "Application
    labels aren't unique."

    Design §10.1 and backlog B-01 both name the *path* ``apps/onboarding/``,
    so the path is kept and the label is made explicit instead. Renaming the
    existing app was the alternative and was rejected: it means renaming live
    tables for no functional gain, against NFR-COMPAT.

    Tables are therefore ``onboarding_sessions_*``.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.onboarding"
    label = "onboarding_sessions"
    verbose_name = "Onboarding Intelligence — Sessions"
