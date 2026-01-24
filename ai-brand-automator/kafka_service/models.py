"""
Kafka Service Models

Models for storing Kafka-related data like audit logs.
"""

from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    """
    Stores API request/response audit logs from Kong Gateway.
    
    These logs are consumed from the gateway-logs Kafka topic and stored
    for compliance, debugging, and analytics purposes.
    """
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    method = models.CharField(max_length=10, null=True, blank=True)
    uri = models.TextField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    latency_ms = models.IntegerField(null=True, blank=True, help_text="Request latency in milliseconds")
    consumer = models.CharField(max_length=255, null=True, blank=True, help_text="Kong consumer username")
    service = models.CharField(max_length=255, null=True, blank=True, help_text="Kong service name")
    route = models.CharField(max_length=255, null=True, blank=True, help_text="Kong route name")
    
    # Additional metadata
    user_agent = models.TextField(null=True, blank=True)
    request_size = models.IntegerField(null=True, blank=True)
    response_size = models.IntegerField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["uri"]),
            models.Index(fields=["status_code"]),
            models.Index(fields=["consumer"]),
        ]
    
    def __str__(self):
        return f"{self.method} {self.uri} - {self.status_code} ({self.timestamp})"


class KafkaEvent(models.Model):
    """
    Stores processed Kafka events for tracking and debugging.
    """
    
    TOPIC_CHOICES = [
        ("gateway-logs", "Gateway Logs"),
        ("raw-ingestion-topic", "Raw Ingestion"),
        ("dlq-events", "Dead Letter Queue"),
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    
    topic = models.CharField(max_length=100, choices=TOPIC_CHOICES, db_index=True)
    key = models.CharField(max_length=255, null=True, blank=True)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Kafka Event"
        verbose_name_plural = "Kafka Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["topic", "status"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return f"{self.topic}: {self.status} ({self.created_at})"


class KafkaConsumerOffset(models.Model):
    """
    Tracks Kafka consumer offsets for manual offset management.
    
    Useful when you need finer control over message processing.
    """
    
    topic = models.CharField(max_length=100)
    partition = models.IntegerField()
    consumer_group = models.CharField(max_length=255)
    offset = models.BigIntegerField()
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Consumer Offset"
        verbose_name_plural = "Consumer Offsets"
        unique_together = ["topic", "partition", "consumer_group"]
    
    def __str__(self):
        return f"{self.topic}[{self.partition}] @ {self.offset}"
