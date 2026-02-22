"""
Orchestration-specific test fixtures.

Reuses global fixtures from conftest.py (tenant, tenant2, user, api_client,
membership_owner, membership_editor, membership_viewer) and adds
orchestration-specific models and mock data.
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from orchestration.models import AnalysisJob, PipelineManifest


@pytest.fixture
def sample_manifest_data():
    """Valid HLD v6.0 Pipeline-as-Code manifest structure."""
    return {
        "nodes": [
            {
                "id": "researcher",
                "type": "internal",
                "handler": "ResearchNode",
                "config": {},
            },
            {
                "id": "strategist",
                "type": "internal",
                "handler": "StrategyNode",
                "config": {},
            },
        ],
        "edges": [["researcher", "strategist"]],
        "global_config": {"model": "gemini-2.0-flash"},
    }


@pytest.fixture
def external_agent_manifest_data():
    """Manifest with external agent nodes (discovery + intelligence)."""
    return {
        "nodes": [
            {
                "id": "intent_router",
                "type": "internal",
                "handler": "RouterNode",
            },
            {
                "id": "web_research",
                "type": "external",
                "url": "http://discovery-agent-svc:8020/v1/search",
            },
            {
                "id": "valuation",
                "type": "external",
                "url": "http://intelligence-agent-svc:8030/v1/iso-calc",
            },
        ],
        "edges": [
            ["intent_router", "web_research"],
            ["web_research", "valuation"],
        ],
        "global_config": {
            "model": "gemini-2.0-flash",
            "temperature": 0.7,
        },
    }


@pytest.fixture
def cyclic_manifest_data():
    """Manifest with circular dependency for validation testing."""
    return {
        "nodes": [
            {"id": "a", "type": "internal", "handler": "NodeA"},
            {"id": "b", "type": "internal", "handler": "NodeB"},
            {"id": "c", "type": "internal", "handler": "NodeC"},
        ],
        "edges": [["a", "b"], ["b", "c"], ["c", "a"]],
    }


@pytest.fixture
def pipeline_manifest(tenant, user, sample_manifest_data):
    """Active pipeline manifest assigned to tenant."""
    return PipelineManifest.objects.create(
        pipeline_id="test-pipeline",
        name="Test Pipeline",
        manifest_data=sample_manifest_data,
        tenant=tenant,
        created_by=user,
    )


@pytest.fixture
def pipeline_manifest_v2(tenant, user, external_agent_manifest_data):
    """Second manifest with external agents."""
    return PipelineManifest.objects.create(
        pipeline_id="external-pipeline",
        name="External Agent Pipeline",
        manifest_data=external_agent_manifest_data,
        tenant=tenant,
        created_by=user,
    )


@pytest.fixture
def inactive_manifest(tenant, user, sample_manifest_data):
    """Deactivated manifest for rejection testing."""
    return PipelineManifest.objects.create(
        pipeline_id="inactive-pipeline",
        name="Inactive Pipeline",
        manifest_data=sample_manifest_data,
        is_active=False,
        tenant=tenant,
        created_by=user,
    )


@pytest.fixture
def analysis_job(tenant, user, pipeline_manifest):
    """Queued analysis job for testing."""
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Analyze brand positioning",
        created_by=user,
    )


@pytest.fixture
def completed_job(tenant, user, pipeline_manifest):
    """Completed analysis job with result data."""
    now = timezone.now()
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Analyze competitors",
        status=AnalysisJob.Status.COMPLETED,
        result_data={"summary": "Analysis complete", "findings": []},
        created_by=user,
        started_at=now - timedelta(minutes=5),
        completed_at=now,
    )


@pytest.fixture
def running_job(tenant, user, pipeline_manifest):
    """Running analysis job for cancel/timeout testing."""
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Market research",
        status=AnalysisJob.Status.RUNNING,
        created_by=user,
        started_at=timezone.now(),
    )


@pytest.fixture
def auto_detect_job(tenant, user):
    """Job without manifest (auto-detect / intent routing mode)."""
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=None,
        input_prompt="Tell me about my brand",
        created_by=user,
    )
