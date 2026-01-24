"""
Django Admin for Kafka Service Models
"""

from django.contrib import admin
from .models import AuditLog, KafkaEvent, KafkaConsumerOffset


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog model"""

    list_display = [
        "timestamp",
        "method",
        "uri",
        "status_code",
        "latency_ms",
        "client_ip",
        "consumer",
    ]
    list_filter = [
        "method",
        "status_code",
        "service",
        "route",
        "timestamp",
    ]
    search_fields = [
        "uri",
        "client_ip",
        "consumer",
    ]
    readonly_fields = [
        "timestamp",
        "client_ip",
        "method",
        "uri",
        "status_code",
        "latency_ms",
        "consumer",
        "service",
        "route",
        "user_agent",
        "request_size",
        "response_size",
    ]
    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        """Audit logs are created by Kafka consumer only"""
        return False

    def has_change_permission(self, request, obj=None):
        """Audit logs are immutable"""
        return False


@admin.register(KafkaEvent)
class KafkaEventAdmin(admin.ModelAdmin):
    """Admin for KafkaEvent model"""

    list_display = [
        "topic",
        "status",
        "created_at",
        "processed_at",
        "short_error",
    ]
    list_filter = [
        "topic",
        "status",
        "created_at",
    ]
    search_fields = [
        "key",
        "error_message",
    ]
    readonly_fields = [
        "topic",
        "key",
        "payload",
        "created_at",
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def short_error(self, obj):
        """Truncated error message for list display"""
        if obj.error_message:
            return (
                obj.error_message[:50] + "..."
                if len(obj.error_message) > 50
                else obj.error_message
            )
        return "-"

    short_error.short_description = "Error"


@admin.register(KafkaConsumerOffset)
class KafkaConsumerOffsetAdmin(admin.ModelAdmin):
    """Admin for KafkaConsumerOffset model"""

    list_display = [
        "topic",
        "partition",
        "consumer_group",
        "offset",
        "updated_at",
    ]
    list_filter = [
        "topic",
        "consumer_group",
    ]
    search_fields = [
        "topic",
        "consumer_group",
    ]
    readonly_fields = [
        "updated_at",
    ]
    ordering = ["topic", "partition"]
