"""SKL-BAA-03: Portfolio loading from Company model + Odoo products."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PortfolioLoader:
    """Load and structure brand portfolio data."""

    async def load(self, company_data: dict[str, Any]) -> dict[str, Any]:
        """Extract portfolio from company context."""
        return {
            "company_name": company_data.get("name", ""),
            "industry": company_data.get("industry", ""),
            "description": company_data.get("description", ""),
            "brand_voice": company_data.get("brand_voice", ""),
            "values": company_data.get("values", ""),
            "target_audience": company_data.get("target_audience", ""),
            "products": company_data.get("products", []),
            "product_count": len(company_data.get("products", [])),
        }
