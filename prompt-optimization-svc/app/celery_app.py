"""Celery application for prompt-optimization-svc.

Standalone Celery instance with Beat schedule for periodic tasks.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "prompt_optimization",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=["app.tasks.mine_golden_examples"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# §14.1: Saturday 03:00 ET = Saturday 07:00 UTC
celery_app.conf.beat_schedule = {
    "mine-golden-examples-weekly": {
        "task": "app.tasks.mine_golden_examples.mine_golden_examples",
        "schedule": crontab(hour=7, minute=0, day_of_week="saturday"),
        "kwargs": {
            "quality_threshold": settings.MINING_QUALITY_THRESHOLD,
            "lookback_days": settings.MINING_LOOKBACK_DAYS,
        },
    },
}
