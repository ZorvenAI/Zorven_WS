"""
Celery configuration for the AI Brand Automator project.
"""

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

app = Celery("brand_automator")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Task routing for specialized workers
# Queue names MUST match the -Q flag in Railway/Procfile worker start commands
app.conf.task_routes = {
    # Route rag_index tasks to ingestion queue (ingestion-worker)
    "rag_index.tasks.*": {"queue": "ingestion"},
    # Route data_ingestion tasks to ingestion queue (worker: -Q ingestion)
    "data_ingestion.tasks.*": {"queue": "ingestion"},
    # Route media_curation tasks to curation queue (worker: -Q curation)
    "media_curation.tasks.*": {"queue": "curation"},
    # Orchestration: dispatch on high_priority, consumers on low_priority
    # to prevent Kafka consumer tasks from starving dispatch tasks.
    "orchestration.tasks.dispatch_job_task": {"queue": "high_priority"},
    "orchestration.tasks.consume_pipeline_results": {"queue": "low_priority"},
    "orchestration.tasks.consume_agent_traces": {"queue": "low_priority"},
    "orchestration.tasks.*": {"queue": "orchestration"},
    # Kafka service consumers on low_priority queue
    "kafka_service.tasks.*": {"queue": "low_priority"},
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
