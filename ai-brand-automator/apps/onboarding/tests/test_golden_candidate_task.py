"""L-02 — Golden-dataset candidate emission tests.

Covers: emit_golden_candidate task payload shape, edit action wiring,
confirm action non-wiring, edit_distance normalization, evidence ref
formats (_build_evidence_ref).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import FieldClassification
from apps.onboarding.tests.factories import (
    evidence_span,
    make_brand_asset,
    make_provenance,
    make_recording,
    make_session,
)
from apps.onboarding.views import _build_evidence_ref
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

PROVENANCE = "/api/v1/onboarding/provenance/"


def _admin(tenant: Tenant) -> tuple[User, APIClient]:
    user = User.objects.create_user(
        username="l02_admin", email="l02@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return user, client


# ── emit_golden_candidate task ──────────────────────────────────────


class TestEmitGoldenCandidateTask:
    @patch("apps.onboarding.tasks.requests.post")
    def test_emit_golden_candidate_calls_oia(self, mock_post, settings):
        from apps.onboarding.tasks import emit_golden_candidate

        settings.OIA_SERVICE_URL = "http://oia:8120"
        settings.OIA_SERVICE_TOKEN = "test-token"

        mock_post.return_value.status_code = 200

        emit_golden_candidate(
            tenant_id="t-1",
            session_id="s-1",
            field_name="legal_name",
            extracted_value="Acme Ltd",
            admin_final_value="Acme Limited",
            edit_distance=0.25,
            classification="KEY",
            evidence_ref="recording:r1:10.0-15.0",
        )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert payload["skill_id"] == "SKL-OIA-13"
        assert payload["tenant_context"]["tenant_id"] == "t-1"
        assert payload["input_context"]["field_name"] == "legal_name"
        assert payload["input_context"]["extracted_value"] == "Acme Ltd"
        assert payload["input_context"]["admin_final_value"] == "Acme Limited"
        assert payload["input_context"]["edit_distance"] == 0.25
        assert payload["input_context"]["classification"] == "KEY"
        assert payload["input_context"]["evidence_ref"] == "recording:r1:10.0-15.0"
        assert payload["input_context"]["candidate_type"] == "field_extraction"

        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Service-Token"] == "test-token"


# ── Edit action triggers golden candidate ───────────────────────────


class TestEditActionWiring:
    @patch("apps.onboarding.tasks.emit_golden_candidate.delay")
    def test_edit_action_triggers_golden_candidate(self, mock_delay, public_tenant):
        user, client = _admin(public_tenant)
        row = make_provenance(
            tenant=public_tenant,
            field_name="legal_name",
            extracted_value="Acme Ltd",
            classification=FieldClassification.KEY,
        )

        response = client.post(
            f"{PROVENANCE}{row.pk}/edit/",
            {"final_value": "Acme Limited"},
            format="json",
        )

        assert response.status_code == 200
        mock_delay.assert_called_once()

        call_kwargs = mock_delay.call_args.kwargs
        assert call_kwargs["field_name"] == "legal_name"
        assert call_kwargs["extracted_value"] == "Acme Ltd"
        assert call_kwargs["admin_final_value"] == "Acme Limited"
        assert call_kwargs["classification"] == "KEY"
        assert 0 < call_kwargs["edit_distance"] <= 1.0

    @patch("apps.onboarding.tasks.emit_golden_candidate.delay")
    def test_confirm_action_does_not_trigger(self, mock_delay, public_tenant):
        user, client = _admin(public_tenant)
        row = make_provenance(
            tenant=public_tenant,
            classification=FieldClassification.KEY,
        )

        response = client.post(f"{PROVENANCE}{row.pk}/confirm/")
        assert response.status_code == 200
        mock_delay.assert_not_called()


# ── Edit distance normalization ─────────────────────────────────────


class TestEditDistanceNormalization:
    @patch("apps.onboarding.tasks.emit_golden_candidate.delay")
    def test_edit_distance_normalized(self, mock_delay, public_tenant):
        """Raw Levenshtein int → normalized float [0,1]."""
        user, client = _admin(public_tenant)
        row = make_provenance(
            tenant=public_tenant,
            extracted_value="abc",
            classification=FieldClassification.SECONDARY,
        )

        client.post(
            f"{PROVENANCE}{row.pk}/edit/",
            {"final_value": "xyz"},
            format="json",
        )

        call_kwargs = mock_delay.call_args.kwargs
        assert 0 < call_kwargs["edit_distance"] <= 1.0
        assert call_kwargs["edit_distance"] == 1.0


# ── Evidence ref formats ────────────────────────────────────────────


class TestBuildEvidenceRef:
    def test_evidence_ref_from_source_span(self, public_tenant):
        row = make_provenance(
            tenant=public_tenant,
            source_span=evidence_span(recording_id="r_42", t_start=10.0, t_end=20.5),
        )
        assert _build_evidence_ref(row) == "recording:r_42:10.0-20.5"

    def test_evidence_ref_from_source_recording(self, public_tenant):
        session = make_session(tenant=public_tenant)
        recording = make_recording(session=session, tenant=public_tenant)
        row = make_provenance(
            session=session,
            tenant=public_tenant,
            source_span=None,
            source_recording=recording,
        )
        assert _build_evidence_ref(row) == f"recording:{recording.pk}"

    def test_evidence_ref_from_source_media(self, public_tenant):
        session = make_session(tenant=public_tenant)
        asset = make_brand_asset(company=session.company)
        row = make_provenance(
            session=session,
            tenant=public_tenant,
            source_span=None,
            source_media=asset,
        )
        assert _build_evidence_ref(row) == f"media:{asset.pk}"

    def test_evidence_ref_unknown_fallback(self):
        """When no source is set, returns 'unknown'."""

        class FakeRow:
            source_span = None
            source_recording_id = None
            source_media_id = None

        assert _build_evidence_ref(FakeRow()) == "unknown"
