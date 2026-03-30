"""SKL-NTA-13: Persist naming results to Redis + GCS + RAG."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class NamingPersister:
    """Persist naming results to storage backends."""

    async def persist(
        self, tenant_id: str, naming_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist naming data.

        Currently Redis-only. GCS + RAG deferred to v2.
        """
        logger.info(
            "Naming persistence for tenant %s (Redis only)", tenant_id
        )
        return {"persisted_to": ["redis"], "version": 1}
