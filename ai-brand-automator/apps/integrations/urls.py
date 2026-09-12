"""Routes for tenant-owned provider connections, at /api/v1/integrations/."""

from django.urls import path

from apps.integrations.views import (
    callback,
    connect,
    connection_status,
    disconnect,
    sync_now,
)

urlpatterns = [
    path("google-calendar/connect/", connect, name="google-calendar-connect"),
    path("google-calendar/callback/", callback, name="google-calendar-callback"),
    path("google-calendar/disconnect/", disconnect, name="google-calendar-disconnect"),
    path("google-calendar/status/", connection_status, name="google-calendar-status"),
    path("google-calendar/sync/", sync_now, name="google-calendar-sync"),
]
