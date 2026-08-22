"""Celery tasks for onboarding session recordings (I-02)."""

import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def trigger_recording_summary(
    self, *, tenant_id, recording_id, session_id, started_at, stopped_at
):
    """Ask the OIA service to summarise a recording.

    Fire-and-forget from the stop action. Retries on 5xx / connection errors;
    4xx is non-retryable (bad payload, not a transient failure).
    """
    url = f"{settings.OIA_SERVICE_URL.rstrip('/')}/v1/execute/skill"
    payload = {
        "skill_id": "SKL-OIA-08",
        "tenant_context": {
            "tenant_id": str(tenant_id),
            "user_id": "system",
            "role": "ADMIN",
            "trace_id": f"celery:{self.request.id or 'unknown'}",
        },
        "input_context": {
            "recording_id": str(recording_id),
            "session_id": str(session_id),
            "started_at": started_at,
            "stopped_at": stopped_at,
        },
    }
    headers = {"X-Service-Token": settings.OIA_SERVICE_TOKEN}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(5, 120))
    except requests.ConnectionError as exc:
        logger.warning("OIA unreachable for recording %s: %s", recording_id, exc)
        raise self.retry(exc=exc)
    except requests.Timeout as exc:
        logger.warning("OIA timed out for recording %s: %s", recording_id, exc)
        raise self.retry(exc=exc)

    if resp.status_code >= 500:
        logger.warning(
            "OIA returned %s for recording %s", resp.status_code, recording_id
        )
        raise self.retry(exc=Exception(f"OIA {resp.status_code}"))

    if resp.status_code >= 400:
        logger.error(
            "OIA rejected recording %s with %s: %s",
            recording_id,
            resp.status_code,
            resp.text[:500],
        )
        return

    logger.info("Summary triggered for recording %s", recording_id)
