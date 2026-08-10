from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """Third-party connections a tenant owns — starting with Google Calendar.

    A separate app rather than more of ``apps.onboarding`` because a provider
    connection is not a property of an onboarding session: it belongs to the
    tenant, outlives every session, and D-03 will sync against it. The D-02
    card names ``apps/integrations/tests/`` directly.

    The label is explicit for the same reason its sibling's is — a default
    label derived from the path would be fine today, and stating it means a
    later move of the directory cannot silently rename tables.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"
    label = "integrations"
    verbose_name = "Integrations — tenant-owned provider connections"
