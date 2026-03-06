"""
Service layer for the orchestration app.

OrchestratorDispatcher — dispatches jobs to the external
pipeline-orchestrator-svc via HTTP and handles cancellation.
"""

import logging

import requests
from decouple import config
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class OrchestratorDispatcher:
    """
    Dispatches analysis jobs to the external pipeline-orchestrator-svc.

    The orchestrator is a separate Python/LangGraph microservice that:
    1. Receives a manifest (agent graph) + input prompt
    2. Executes agents in dependency order
    3. Calls back to our /callback/ endpoint with progress and results

    Configuration (via decouple.config):
        ORCHESTRATOR_URL: Base URL of the pipeline-orchestrator-svc
        ORCHESTRATOR_SERVICE_TOKEN: Auth token for dispatch calls
        ORCHESTRATOR_CALLBACK_TOKEN: Shared secret for callback auth
        ORCHESTRATOR_TIMEOUT: HTTP timeout for dispatch call (seconds)
    """

    def __init__(self):
        self.orchestrator_url = config(
            "ORCHESTRATOR_URL", default="http://localhost:8010"
        )
        self.service_token = config(
            "ORCHESTRATOR_SERVICE_TOKEN", default="dev-service-token"
        )
        self.callback_token = config(
            "ORCHESTRATOR_CALLBACK_TOKEN", default="dev-callback-token"
        )
        self.timeout = config("ORCHESTRATOR_TIMEOUT", default=30, cast=int)

    def dispatch(self, job):
        """
        POST the job to the orchestrator service.

        Builds payload per Service Interaction Contract 1 (HLD v6.0).
        Includes tenant_context for secure data isolation.

        Returns True on successful dispatch (202), False on failure.
        Updates job.status to RUNNING on success, FAILED on error.
        """
        from .models import AnalysisJob

        payload = self._build_payload(job)

        try:
            response = requests.post(
                f"{self.orchestrator_url}/v1/jobs/dispatch",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Token": self.service_token,
                },
                timeout=self.timeout,
            )

            if response.status_code == 202:
                job.status = AnalysisJob.Status.RUNNING
                job.started_at = timezone.now()
                job.save(update_fields=["status", "started_at", "updated_at"])
                logger.info("Job %s dispatched successfully", job.job_id)
                return True

            # 4xx = non-retryable (bad request, auth, etc.) → mark failed
            if 400 <= response.status_code < 500:
                logger.error(
                    "Non-retryable dispatch failure for job %s: HTTP %s — %s",
                    job.job_id,
                    response.status_code,
                    response.text[:500],
                )
                job.status = AnalysisJob.Status.FAILED
                job.error_message = f"Dispatch failed: HTTP {response.status_code}"
                job.completed_at = timezone.now()
                job.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "completed_at",
                        "updated_at",
                    ]
                )
                return False

            # 5xx = retryable → leave job in current status for Celery retry
            logger.warning(
                "Retryable dispatch failure for job %s: HTTP %s — %s",
                job.job_id,
                response.status_code,
                response.text[:500],
            )
            return False

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Orchestrator unreachable for job %s at %s",
                job.job_id,
                self.orchestrator_url,
            )
            # Leave job in QUEUED status for retry
            return False

        except requests.exceptions.Timeout:
            logger.error(
                "Dispatch timeout for job %s after %ds",
                job.job_id,
                self.timeout,
            )
            return False

        except requests.exceptions.RequestException as exc:
            logger.error(
                "Dispatch error for job %s: %s",
                job.job_id,
                str(exc),
            )
            return False

    def cancel(self, job):
        """
        POST cancel request to the orchestrator (Contract 3).

        Returns True if orchestrator accepted the cancel, False otherwise.
        """
        try:
            response = requests.post(
                f"{self.orchestrator_url}/v1/jobs/{job.job_id}/cancel",
                headers={"X-Service-Token": self.service_token},
                timeout=self.timeout,
            )
            if response.status_code == 200:
                logger.info("Job %s cancel accepted", job.job_id)
                return True
            logger.warning(
                "Cancel rejected for job %s: HTTP %s",
                job.job_id,
                response.status_code,
            )
            return False

        except requests.exceptions.RequestException as exc:
            logger.error(
                "Cancel request failed for job %s: %s",
                job.job_id,
                str(exc),
            )
            return False

    def _build_payload(self, job):
        """Build dispatch payload per Service Interaction Contract 1."""
        from .models import PipelineManifest

        payload = {
            "job_id": str(job.job_id),
            "manifest": (job.manifest.manifest_data if job.manifest else None),
            "input_prompt": job.input_prompt,
            "input_context": job.input_context or {},
            "tenant_context": self._build_tenant_context(job),
            "callback_url": self._build_callback_url(job),
        }

        # When manifest is null (auto-detect mode), include catalog
        # with full manifest_data so orchestrator can execute after routing
        if job.manifest is None:
            payload["available_manifests"] = list(
                PipelineManifest.objects.filter(is_active=True).values(
                    "pipeline_id", "name", "description", "manifest_data"
                )
            )

        return payload

    def _build_tenant_context(self, job):
        """
        Build tenant-scoped context for secure data isolation.

        Resolves the tenant's GCS bucket paths and RAG data store ID
        so the orchestrator only accesses the correct tenant's data.
        """
        tenant = job.tenant
        if not tenant:
            return {}

        gs_bucket = getattr(settings, "GS_BUCKET_NAME", "brand-automator")
        return {
            "tenant_id": str(tenant.id),
            "gcs_raw_bucket": f"{gs_bucket}/{tenant.id}/",
            "gcs_processed_bucket": f"{gs_bucket}-curated/{tenant.id}/",
            "rag_data_store_id": tenant.get_data_store_id(),
        }

    def _build_callback_url(self, job):
        """Build the callback URL for this job.

        Uses ``CALLBACK_BASE_URL`` which must point to the **web**
        service's private networking URL (e.g.
        ``http://previsionws.railway.internal:8000`` on Railway).

        Note: Do NOT use ``RAILWAY_PRIVATE_DOMAIN`` here — dispatch runs
        inside a Celery worker which is a separate Railway service with
        its own private domain.  The callback must always target the
        web service.
        """
        base_url = config(
            "CALLBACK_BASE_URL",
            default=config("BACKEND_URL", default="http://localhost:8001"),
        ).rstrip("/")
        if "localhost" in base_url or "127.0.0.1" in base_url:
            logger.warning(
                "Callback base URL is '%s' — pipeline callbacks will "
                "fail if the orchestrator runs on a different host. "
                "Set CALLBACK_BASE_URL to the internal service URL "
                "(e.g. http://backend:8001 or "
                "http://<service>.railway.internal:<port>).",
                base_url,
            )
        callback_url = f"{base_url}/api/v1/orchestration/jobs/{job.job_id}/callback/"
        logger.info("Callback URL for job %s: %s", job.job_id, callback_url)
        return callback_url
