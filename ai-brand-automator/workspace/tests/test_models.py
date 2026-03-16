"""Tests for workspace models."""

import uuid

import pytest
from django.db import IntegrityError

from orchestration.models import AnalysisJob, PipelineManifest
from workspace.models import ChatWorkspaceLink, UserWorkflow, WorkflowSnapshot


@pytest.mark.django_db
class TestUserWorkflow:
    """Tests for UserWorkflow model."""

    def test_create_workflow(self, user_workflow):
        assert user_workflow.pk is not None
        assert user_workflow.workflow_id is not None
        assert user_workflow.name == "Test Workflow"
        assert user_workflow.source == UserWorkflow.Source.CREATED
        assert user_workflow.is_active is True
        assert user_workflow.execution_count == 0

    def test_str(self, user_workflow):
        assert str(user_workflow.workflow_id) in str(user_workflow)
        assert "Test Workflow" in str(user_workflow)

    def test_workflow_id_is_uuid(self, user_workflow):
        assert isinstance(user_workflow.workflow_id, uuid.UUID)

    def test_ordering_by_updated_at(self, workflow_factory):
        w1 = workflow_factory(name="First")
        w2 = workflow_factory(name="Second")
        workflows = list(UserWorkflow.objects.all())
        assert workflows[0] == w2
        assert workflows[1] == w1

    def test_soft_delete(self, user_workflow):
        user_workflow.is_active = False
        user_workflow.save(update_fields=["is_active"])
        assert (
            UserWorkflow.objects.filter(pk=user_workflow.pk, is_active=True).count()
            == 0
        )
        assert (
            UserWorkflow.objects.filter(pk=user_workflow.pk, is_active=False).count()
            == 1
        )

    def test_unique_name_per_tenant_constraint(
        self, user_workflow, public_tenant, user
    ):
        """Active workflows must have unique names per tenant."""
        manifest = PipelineManifest.objects.create(
            pipeline_id="dup-test",
            name="Dup",
            manifest_data={
                "nodes": [{"id": "m", "type": "internal", "handler": "ManagerNode"}],
                "edges": [],
            },
            tenant=public_tenant,
        )
        with pytest.raises(IntegrityError):
            UserWorkflow.objects.create(
                name="Test Workflow",  # same name as user_workflow
                manifest=manifest,
                tenant=public_tenant,
                created_by=user,
            )

    def test_duplicate_name_allowed_if_inactive(
        self, user_workflow, public_tenant, user
    ):
        """Inactive workflows don't trigger the unique constraint."""
        user_workflow.is_active = False
        user_workflow.save(update_fields=["is_active"])

        manifest = PipelineManifest.objects.create(
            pipeline_id="dup-ok",
            name="Dup OK",
            manifest_data={
                "nodes": [{"id": "m", "type": "internal", "handler": "ManagerNode"}],
                "edges": [],
            },
            tenant=public_tenant,
        )
        w = UserWorkflow.objects.create(
            name="Test Workflow",
            manifest=manifest,
            tenant=public_tenant,
            created_by=user,
        )
        assert w.pk is not None

    def test_source_choices(self):
        assert UserWorkflow.Source.CREATED == "created"
        assert UserWorkflow.Source.CLONED == "cloned"
        assert UserWorkflow.Source.TEMPLATE == "template"
        assert UserWorkflow.Source.CHAT == "chat"


@pytest.mark.django_db
class TestWorkflowSnapshot:
    """Tests for WorkflowSnapshot model."""

    def test_create_snapshot(self, user_workflow, public_tenant):
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
            status=AnalysisJob.Status.QUEUED,
        )
        snapshot = WorkflowSnapshot.objects.create(
            workflow=user_workflow,
            job=job,
            manifest_snapshot=user_workflow.manifest.manifest_data,
            layout_snapshot=user_workflow.layout_data,
            tenant=public_tenant,
        )
        assert snapshot.snapshot_id is not None
        assert snapshot.manifest_snapshot == user_workflow.manifest.manifest_data

    def test_snapshot_str(self, user_workflow, public_tenant):
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
        )
        snapshot = WorkflowSnapshot.objects.create(
            workflow=user_workflow,
            job=job,
            manifest_snapshot={},
            layout_snapshot={},
            tenant=public_tenant,
        )
        assert "Test Workflow" in str(snapshot)

    def test_one_snapshot_per_job(self, user_workflow, public_tenant):
        """Each job can only have one snapshot (OneToOne)."""
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
        )
        WorkflowSnapshot.objects.create(
            workflow=user_workflow,
            job=job,
            manifest_snapshot={},
            layout_snapshot={},
            tenant=public_tenant,
        )
        with pytest.raises(IntegrityError):
            WorkflowSnapshot.objects.create(
                workflow=user_workflow,
                job=job,
                manifest_snapshot={},
                layout_snapshot={},
                tenant=public_tenant,
            )


@pytest.mark.django_db
class TestChatWorkspaceLink:
    """Tests for ChatWorkspaceLink model."""

    def test_create_link(self, user_workflow, public_tenant):
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
        )
        link = ChatWorkspaceLink.objects.create(
            job=job,
            workflow=user_workflow,
            chat_session_id="session-123",
            tenant=public_tenant,
        )
        assert link.pk is not None
        assert link.chat_session_id == "session-123"

    def test_one_link_per_job(self, user_workflow, public_tenant):
        """Each job can only be linked once (OneToOne)."""
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
        )
        ChatWorkspaceLink.objects.create(
            job=job,
            workflow=user_workflow,
            chat_session_id="s1",
            tenant=public_tenant,
        )
        with pytest.raises(IntegrityError):
            ChatWorkspaceLink.objects.create(
                job=job,
                workflow=user_workflow,
                chat_session_id="s2",
                tenant=public_tenant,
            )
