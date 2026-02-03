"""
Celery Tasks for RAG Index Service.

Provides async task processing for document synchronization.
"""

from rag_index.tasks.sync_tasks import (
    sync_document,
    batch_sync_documents,
    retry_failed_syncs,
)

__all__ = [
    "sync_document",
    "batch_sync_documents",
    "retry_failed_syncs",
]
