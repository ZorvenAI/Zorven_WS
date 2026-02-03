"""
Services Layer for RAG Index Service.

Provides the core business logic orchestration using dependency injection.
"""

from rag_index.services.sync_orchestrator import SyncOrchestrator

__all__ = [
    "SyncOrchestrator",
]
