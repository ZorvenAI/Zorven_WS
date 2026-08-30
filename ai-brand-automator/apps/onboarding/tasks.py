"""Celery tasks for onboarding session recordings (I-02, J-01, L-02)."""

import hashlib
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

    try:
        body = resp.json()
    except ValueError:
        body = {}

    if body.get("status") == "FAILED":
        output = body.get("output", {})
        detail = output.get("error", "unknown") if isinstance(output, dict) else ""
        logger.error(
            "OIA skill failed for recording %s: %s",
            recording_id,
            str(detail)[:500],
        )
        raise self.retry(exc=Exception("OIA skill returned FAILED"))

    logger.info("Summary triggered for recording %s", recording_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def dispatch_process(self, *, session_id, tenant_id, manifest, manifest_hash):
    """Ask the OIA service to process session evidence (J-01, §10.2.2).

    Fire-and-forget from the process action. On 202 stores the job_id on
    the session. Retries on 5xx / connection errors; 4xx is non-retryable.
    """
    from apps.onboarding.models import OnboardingSession

    idempotency_key = hashlib.sha256(
        f"{session_id}:{manifest_hash}".encode()
    ).hexdigest()

    url = f"{settings.OIA_SERVICE_URL.rstrip('/')}/v1/process"
    callback_url = (
        f"{settings.BACKEND_URL.rstrip('/')}"
        f"/api/v1/onboarding/internal/sessions/{session_id}/process/callback/"
    )
    payload = {
        "tenant_context": {
            "tenant_id": str(tenant_id),
            "user_id": "system",
            "role": "ADMIN",
            "trace_id": f"celery:{self.request.id or 'unknown'}",
        },
        "session_id": str(session_id),
        "evidence_manifest": manifest,
        "options": {},
        "callback_url": callback_url,
    }
    headers = {
        "X-Service-Token": settings.OIA_SERVICE_TOKEN,
        "Idempotency-Key": idempotency_key,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(5, 30))
    except requests.ConnectionError as exc:
        logger.warning("OIA unreachable for process %s: %s", session_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _revert_to_gathered(session_id)
            return
    except requests.Timeout as exc:
        logger.warning("OIA timed out for process %s: %s", session_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _revert_to_gathered(session_id)
            return

    if resp.status_code >= 500:
        logger.warning("OIA returned %s for process %s", resp.status_code, session_id)
        try:
            raise self.retry(exc=Exception(f"OIA {resp.status_code}"))
        except self.MaxRetriesExceededError:
            _revert_to_gathered(session_id)
            return

    if resp.status_code >= 400:
        logger.error(
            "OIA rejected process %s with %s: %s",
            session_id,
            resp.status_code,
            resp.text[:500],
        )
        _revert_to_gathered(session_id)
        return

    try:
        body = resp.json()
    except ValueError:
        body = {}

    job_id = body.get("job_id", "")
    if job_id:
        OnboardingSession.objects.filter(pk=session_id).update(
            process_job_id=str(job_id)[:64]
        )

    logger.info("Process dispatched for session %s, job_id=%s", session_id, job_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def emit_golden_candidate(
    self,
    *,
    tenant_id,
    session_id,
    field_name,
    extracted_value,
    admin_final_value,
    edit_distance,
    classification,
    evidence_ref,
    prompt_id="oia.extract_fields",
):
    """Ask OIA to record a golden-dataset candidate (L-02, §17.3).

    Fire-and-forget from the edit action. Retries on 5xx / connection errors;
    4xx is non-retryable. A failure here must never surface to the operator.
    """
    url = f"{settings.OIA_SERVICE_URL.rstrip('/')}/v1/execute/skill"
    payload = {
        "skill_id": "SKL-OIA-13",
        "tenant_context": {
            "tenant_id": str(tenant_id),
            "user_id": "system",
            "role": "ADMIN",
            "trace_id": f"celery:{self.request.id or 'unknown'}",
        },
        "input_context": {
            "candidate_type": "field_extraction",
            "session_id": str(session_id),
            "field_name": field_name,
            "extracted_value": extracted_value,
            "admin_final_value": admin_final_value,
            "edit_distance": edit_distance,
            "classification": classification,
            "evidence_ref": evidence_ref,
            "prompt_id": prompt_id,
        },
    }
    headers = {"X-Service-Token": settings.OIA_SERVICE_TOKEN}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(5, 30))
    except requests.ConnectionError as exc:
        logger.warning("OIA unreachable for golden candidate %s: %s", field_name, exc)
        raise self.retry(exc=exc)
    except requests.Timeout as exc:
        logger.warning("OIA timed out for golden candidate %s: %s", field_name, exc)
        raise self.retry(exc=exc)

    if resp.status_code >= 500:
        logger.warning(
            "OIA returned %s for golden candidate %s", resp.status_code, field_name
        )
        raise self.retry(exc=Exception(f"OIA {resp.status_code}"))

    if resp.status_code >= 400:
        logger.error(
            "OIA rejected golden candidate %s with %s: %s",
            field_name,
            resp.status_code,
            resp.text[:500],
        )
        return

    logger.info("Golden candidate emitted for field %s", field_name)


def _revert_to_gathered(session_id):
    """Revert a session from PROCESSING → GATHERED so it is not stuck."""
    from apps.onboarding.models import OnboardingSession, SessionStatus
    from apps.onboarding.services.session_state import transition

    try:
        session = OnboardingSession.objects.get(
            pk=session_id, status=SessionStatus.PROCESSING
        )
        transition(session, SessionStatus.GATHERED)
    except OnboardingSession.DoesNotExist:
        logger.warning(
            "revert_to_gathered: session %s not found or not PROCESSING", session_id
        )
