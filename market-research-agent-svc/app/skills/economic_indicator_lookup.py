"""SKL-MRA-04: Economic Indicator Lookup — World Bank data."""

import logging
import time
from typing import Any

from app.services.api_clients import WorldBankClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class EconomicIndicatorLookup(BaseSkill):
    """Fetches economic indicators from World Bank Open Data API."""

    meta = SkillMeta(
        skill_id="SKL-MRA-04",
        name="economic_indicator_lookup",
        description="Fetch economic indicators (GDP, inflation, etc.) from World Bank",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=30000,
        circuit_breaker_dependency="worldbank",
    )

    def __init__(self, world_bank_client: WorldBankClient) -> None:
        self.world_bank_client = world_bank_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Look up economic indicators.

        input_data keys:
          - country (str): ISO alpha-2 code or 'WLD' (default 'WLD')
          - indicators (list[str]): Indicator names (e.g. ['gdp', 'inflation'])
          - period (str): Year range (default '2019:2024')
        """
        start = time.monotonic()
        country = input_data.get("country", "WLD")
        indicators = input_data.get("indicators", ["gdp", "gdp_growth"])
        period = input_data.get("period", "2019:2024")

        if not indicators:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No indicators specified",
                duration_ms=_elapsed(start),
            )

        try:
            raw_data = await self.world_bank_client.get_multiple_indicators(
                indicators[:5], country=country, date_range=period
            )

            # Format into structured output
            formatted_indicators: list[dict[str, Any]] = []
            for name, values in raw_data.items():
                if values:
                    latest = values[0]
                    formatted_indicators.append(
                        {
                            "indicator_id": name,
                            "indicator_name": latest.get("indicator", name),
                            "country": latest.get("country", country),
                            "latest_value": latest.get("value"),
                            "latest_date": latest.get("date"),
                            "values": [
                                {"date": v.get("date"), "value": v.get("value")}
                                for v in values[:10]
                            ],
                        }
                    )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "indicators": formatted_indicators,
                    "data_source": "World Bank Open Data",
                    "country": country,
                    "period": period,
                    "indicator_count": len(formatted_indicators),
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("EconomicIndicatorLookup failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
