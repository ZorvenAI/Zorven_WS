"""Kafka topic configuration per §8.1.

Topic retention and naming for prompt lifecycle events.
"""

# Lifecycle events topic
LIFECYCLE_TOPIC = "prompt-lifecycle-events"

# §8.1: 30-day retention for lifecycle events (AC-1)
LIFECYCLE_TOPIC_RETENTION_MS = 30 * 24 * 3600 * 1000  # 30 days in milliseconds

# Audit topic
AUDIT_TOPIC = "poi-optimization-audit-topic"
AUDIT_TOPIC_RETENTION_MS = 90 * 24 * 3600 * 1000  # 90 days

# Trace topic
TRACE_TOPIC = "agent-trace-topic"
TRACE_TOPIC_RETENTION_MS = 7 * 24 * 3600 * 1000  # 7 days
