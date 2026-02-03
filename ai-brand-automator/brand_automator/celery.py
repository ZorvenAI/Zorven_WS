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
app.conf.task_routes = {
    # Route rag_index tasks to dedicated queue
    "rag_index.tasks.*": {"queue": "rag-sync-queue"},
    # Route data_ingestion tasks to ingestion queue
    "data_ingestion.tasks.*": {"queue": "ingestion-queue"},
    # Route media_curation tasks to curation queue
    "media_curation.tasks.*": {"queue": "curation-queue"},
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
