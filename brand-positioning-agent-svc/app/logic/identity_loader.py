"""SKL-BPA-04: Brand Identity Loader.

Loads brand identity anchor from tenant context and company model.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class IdentityLoader:
    """Loads brand identity context for positioning."""

    async def load(
        self,
        tenant_context: dict[str, Any],
        input_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Load brand identity from available sources.

        Returns:
            Brand identity context for positioning analysis.
        """
        return {
            "company_name": (
                tenant_context.get("company_name", "")
                or input_context.get("company_name", "")
            ),
            "sector": input_context.get("sector", ""),
            "brand_values": input_context.get("brand_values", []),
            "brand_voice": input_context.get("brand_voice", ""),
            "target_market": input_context.get("target_market", ""),
            "mission_statement": input_context.get("mission_statement", ""),
        }
