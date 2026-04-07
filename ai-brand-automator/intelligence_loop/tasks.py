"""Celery tasks for the intelligence_loop app.

expire_pending_wf2_requests — flips ``WF2RerunRequest`` rows from
``pending`` to ``expired`` once their ``expires_at`` has passed. Run
hourly via Celery Beat.
"""

import logging

from celery import shared_task
from django.utils import timezone

from .models import WF2RerunRequest

logger = logging.getLogger(__name__)


@shared_task(name="intelligence_loop.tasks.expire_pending_wf2_requests")
def expire_pending_wf2_requests() -> int:
    """Mark expired pending WF2 approval requests as ``expired``.

    Returns the number of rows updated.
    """
    now = timezone.now()
    qs = WF2RerunRequest.objects.filter(status="pending", expires_at__lt=now)
    updated = qs.update(status="expired", updated_at=now)
    if updated:
        logger.info("Expired %d pending WF2 rerun requests", updated)
    return updated
