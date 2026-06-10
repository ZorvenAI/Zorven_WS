"""Celery application for prompt-optimization-svc.

Standalone Celery instance with Beat schedule for periodic tasks.
All schedules per §14.1.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "prompt_optimization",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=[
        "app.tasks.mine_golden_examples",
        "app.tasks.optimize_wf1_pipeline",
        "app.tasks.optimize_wf2_pipeline",
        "app.tasks.optimize_wf3_pipeline",
        "app.tasks.prompt_health_check",
    ],
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

# §14.1 Celery Beat Schedule
celery_app.conf.beat_schedule = {
    # Weekly: Saturday 07:00 UTC (03:00 ET)
    "mine-golden-examples-weekly": {
        "task": "app.tasks.mine_golden_examples.mine_golden_examples",
        "schedule": crontab(hour=7, minute=0, day_of_week="saturday"),
        "kwargs": {
            "quality_threshold": settings.MINING_QUALITY_THRESHOLD,
            "lookback_days": settings.MINING_LOOKBACK_DAYS,
        },
    },
    # Monthly: 2nd Sunday 06:00 UTC (02:00 ET)
    "optimize-wf1-pipeline-monthly": {
        "task": "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline",
        "schedule": crontab(
            hour=6, minute=0, day_of_week="sunday", day_of_month="8-14"
        ),
    },
    # Monthly: 3rd Sunday 06:00 UTC (02:00 ET)
    "optimize-wf2-pipeline-monthly": {
        "task": "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline",
        "schedule": crontab(
            hour=6, minute=0, day_of_week="sunday", day_of_month="15-21"
        ),
    },
    # Weekly (Sunday): task self-skips based on tenant schedule config (AC-2)
    "optimize-wf3-creative-pipeline": {
        "task": "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
        "schedule": crontab(hour=6, minute=0, day_of_week="sunday"),
    },
    # Weekly (Sunday): follows same schedule as creative pipeline
    "optimize-wf3-optimization-loop": {
        "task": "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop",
        "schedule": crontab(hour=6, minute=30, day_of_week="sunday"),
    },
    # Daily: 10:00 UTC (06:00 ET)
    "prompt-health-check-daily": {
        "task": "app.tasks.prompt_health_check.prompt_health_check",
        "schedule": crontab(hour=10, minute=0),
    },
}
