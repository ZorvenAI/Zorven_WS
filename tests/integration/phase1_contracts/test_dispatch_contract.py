"""Contract tests: Django -> Orchestrator dispatch endpoint.

Validates that the orchestrator accepts payloads matching
OrchestratorDispatcher._build_payload() from ai-brand-automator.
"""

import pytest

from tests.integration.conftest import (
    BRAND_ANALYSIS_MANIFEST,
    ALL_AVAILABLE_MANIFESTS,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
    make_job_id,
)


@pytest.mark.integration
class TestDispatchContract:
    """POST /v1/jobs/dispatch contract validation."""

    async def test_dispatch_returns_202_accepted(self, http_client, service_headers):
        """Valid payload returns 202 with {"status": "accepted"}."""
        payload = make_dispatch_payload(manifest=BRAND_ANALYSIS_MANIFEST)
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"

    async def test_dispatch_rejects_missing_job_id(self, http_client, service_headers):
        """Missing required field job_id returns 422."""
        payload = make_dispatch_payload(manifest=BRAND_ANALYSIS_MANIFEST)
        del payload["job_id"]
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 422

    async def test_dispatch_rejects_bad_auth(self, http_client):
        """Wrong or missing X-Service-Token returns 401."""
        payload = make_dispatch_payload(manifest=BRAND_ANALYSIS_MANIFEST)
        # No auth header
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
        )
        assert resp.status_code in (401, 403)

        # Wrong token
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code in (401, 403)

    async def test_dispatch_accepts_null_manifest(self, http_client, service_headers):
        """Auto-detect mode (manifest=null) is accepted."""
        payload = make_dispatch_payload(
            manifest=None,
            available_manifests=ALL_AVAILABLE_MANIFESTS,
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

    async def test_dispatch_accepts_manifest_with_nodes(
        self, http_client, service_headers
    ):
        """Full manifest with nodes/edges/global_config is accepted."""
        payload = make_dispatch_payload(manifest=BRAND_ANALYSIS_MANIFEST)
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

    async def test_dispatch_schema_matches_django_payload(
        self, http_client, service_headers
    ):
        """Payload built like _build_payload() is accepted.

        This mirrors the real Django payload structure including tenant_context
        and callback_url format.
        """
        job_id = make_job_id()
        payload = {
            "job_id": job_id,
            "manifest": BRAND_ANALYSIS_MANIFEST,
            "input_prompt": "Analyze brand positioning for Acme Corp",
            "input_context": {"company_id": 42},
            "tenant_context": {
                "tenant_id": "1",
                "gcs_raw_bucket": "brand-automator/1/",
                "gcs_processed_bucket": "brand-automator-curated/1/",
                "rag_data_store_id": "ds-123",
            },
            "callback_url": (
                f"http://backend:8001/api/v1/orchestration/jobs/{job_id}/callback/"
            ),
        }
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202
