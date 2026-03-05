"""
Unit Tests for DB-to-RAG signal handlers.

Tests that post_save signals correctly dispatch sync tasks with
the right model name, pk, and tenant_id. Mocks Celery to avoid
actual task execution.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from rag_index.signals import (
    sync_company_to_rag,
    sync_analysis_job_to_rag,
    sync_chat_message_to_rag,
    sync_ai_generation_to_rag,
    sync_content_calendar_to_rag,
)


@pytest.fixture
def mock_sync_task():
    with patch(
        "rag_index.signals.sync_model_to_rag",
        create=True,
    ) as mock_task:
        # Need to patch the import inside signal handlers
        yield mock_task


class TestSyncCompanyToRag:
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches_on_create(self, mock_task):
        instance = SimpleNamespace(pk=42, tenant=SimpleNamespace(id=7))
        sync_company_to_rag(sender=None, instance=instance, created=True)
        mock_task.apply_async.assert_called_once_with(
            args=["Company", 42, "7"],
            countdown=0,
        )

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches_on_update_with_debounce(self, mock_task):
        instance = SimpleNamespace(pk=42, tenant=SimpleNamespace(id=7))
        sync_company_to_rag(sender=None, instance=instance, created=False)
        mock_task.apply_async.assert_called_once_with(
            args=["Company", 42, "7"],
            countdown=5,
        )

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_handles_celery_down(self, mock_task):
        mock_task.apply_async.side_effect = Exception("Redis down")
        instance = SimpleNamespace(pk=42, tenant=SimpleNamespace(id=7))
        # Should not raise
        sync_company_to_rag(sender=None, instance=instance, created=True)

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_no_tenant(self, mock_task):
        instance = SimpleNamespace(pk=42, tenant=None)
        sync_company_to_rag(sender=None, instance=instance, created=True)
        mock_task.apply_async.assert_called_once_with(
            args=["Company", 42, None],
            countdown=0,
        )


class TestSyncAnalysisJobToRag:
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches_completed_job(self, mock_task):
        instance = SimpleNamespace(
            pk=99, status="completed", tenant=SimpleNamespace(id=7)
        )
        sync_analysis_job_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_called_once_with(
            args=["AnalysisJob", 99, "7"],
            countdown=2,
        )

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_running_job(self, mock_task):
        instance = SimpleNamespace(
            pk=99, status="running", tenant=SimpleNamespace(id=7)
        )
        sync_analysis_job_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_queued_job(self, mock_task):
        instance = SimpleNamespace(pk=99, status="queued", tenant=SimpleNamespace(id=7))
        sync_analysis_job_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()


class TestSyncChatMessageToRag:
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches_assistant_message(self, mock_task):
        instance = SimpleNamespace(
            pk=500,
            role="assistant",
            session=SimpleNamespace(tenant=SimpleNamespace(id=7)),
        )
        sync_chat_message_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_called_once_with(
            args=["ChatMessage", 500, "7"],
            countdown=10,
        )

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_user_message(self, mock_task):
        instance = SimpleNamespace(pk=501, role="user")
        sync_chat_message_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_system_message(self, mock_task):
        instance = SimpleNamespace(pk=502, role="system")
        sync_chat_message_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()


class TestSyncAIGenerationToRag:
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches(self, mock_task):
        instance = SimpleNamespace(pk=200, tenant=SimpleNamespace(id=7))
        sync_ai_generation_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_called_once_with(
            args=["AIGeneration", 200, "7"],
            countdown=5,
        )


class TestSyncContentCalendarToRag:
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_dispatches_published(self, mock_task):
        instance = SimpleNamespace(
            pk=300, status="published", tenant=SimpleNamespace(id=7)
        )
        sync_content_calendar_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_called_once_with(
            args=["ContentCalendar", 300, "7"],
            countdown=2,
        )

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_draft(self, mock_task):
        instance = SimpleNamespace(pk=300, status="draft", tenant=SimpleNamespace(id=7))
        sync_content_calendar_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()

    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_skips_scheduled(self, mock_task):
        instance = SimpleNamespace(
            pk=300, status="scheduled", tenant=SimpleNamespace(id=7)
        )
        sync_content_calendar_to_rag(sender=None, instance=instance)
        mock_task.apply_async.assert_not_called()
