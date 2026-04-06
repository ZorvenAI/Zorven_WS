"""Celery application for Campaign Optimization Agent.

Standalone Celery instance using Redis DB 24 as broker.
Defines 4 periodic tasks via Beat schedule:
- optimization-tick-hourly: campaigns < 7 days old (every 3600s)
- optimization-tick-4h: campaigns 7-30 days old (every 14400s)
- optimization-tick-daily: campaigns > 30 days old (crontab 06:00 UTC)
- expire-stale-recommendations: cleanup every 3600s
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "campaign-optimization-agent",
    broker=settings.CELERY_BROKER_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    result_backend=settings.CELERY_BROKER_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

celery_app.conf.beat_schedule = {
    "optimization-tick-hourly": {
        "task": "app.tasks.run_optimization_tick",
        "schedule": 3600,
        "kwargs": {"campaign_age_max_days": 7},
    },
    "optimization-tick-4h": {
        "task": "app.tasks.run_optimization_tick",
        "schedule": 14400,
        "kwargs": {
            "campaign_age_min_days": 7,
            "campaign_age_max_days": 30,
        },
    },
    "optimization-tick-daily": {
        "task": "app.tasks.run_optimization_tick",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {"campaign_age_min_days": 30},
    },
    "expire-stale-recommendations": {
        "task": "app.tasks.expire_stale_recommendations",
        "schedule": 3600,
    },
}
