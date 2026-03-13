"""SKL-APA-05c: Odoo CRM Customer Extractor — Customer segments via XML-RPC."""

import logging
import time
from collections import defaultdict
from typing import Any

from app.cache.redis_manager import RedisManager
from app.services.odoo_rpc_client import OdooRPCClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SUFFICIENT_DATA_THRESHOLD = 10


class OdooCRMCustomerExtractor(BaseSkill):
    """Extract CRM customer segments from Odoo for persona grounding."""

    meta = SkillMeta(
        skill_id="SKL-APA-05c",
        name="odoo_crm_customer_extractor",
        description=(
            "Extract CRM customer data via Odoo XML-RPC. Groups by "
            "industry, country, and company size. Sets has_sufficient_data "
            "when customer_count >= 10 for CRM-grounded persona naming."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=45000,
        circuit_breaker_dependency="odoo_crm",
    )

    def __init__(
        self,
        odoo_client: OdooRPCClient,
        redis_manager: RedisManager,
    ) -> None:
        self.odoo_client = odoo_client
        self.redis_manager = redis_manager

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Extract CRM customer segments from Odoo.

        input_data keys:
          - prompt (str): Analysis query
        """
        start = time.monotonic()
        tenant_id = context.tenant_id

        # Check cache first
        cached = await self.redis_manager.get_odoo_crm_cache(tenant_id)
        if cached:
            logger.info("Using cached CRM data for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=cached,
                duration_ms=_elapsed(start),
            )

        try:
            # Fetch customers (res.partner)
            customers = await self.odoo_client.search_read(
                "res.partner",
                domain=[
                    ("customer_rank", ">", 0),
                    ("is_company", "=", True),
                ],
                fields=[
                    "id",
                    "name",
                    "industry_id",
                    "country_id",
                    "category_id",
                    "company_type",
                ],
                limit=500,
            )

            customer_count = len(customers)
            has_sufficient_data = customer_count >= _SUFFICIENT_DATA_THRESHOLD

            # Fetch leads/opportunities for win rate
            leads = await self.odoo_client.search_read(
                "crm.lead",
                domain=[("type", "=", "opportunity")],
                fields=["id", "partner_id", "stage_id", "expected_revenue"],
                limit=500,
            )

            # Fetch sales orders for revenue data
            orders = await self.odoo_client.search_read(
                "sale.order",
                domain=[("state", "in", ["sale", "done"])],
                fields=["id", "partner_id", "amount_total"],
                limit=500,
            )

            # Segment customers
            segments = _segment_customers(customers, leads, orders)

            # Build context
            context_parts = [
                f"Odoo CRM Data ({customer_count} customers, "
                f"{len(leads)} opportunities, {len(orders)} orders):",
            ]
            for seg_name, seg_data in segments.items():
                context_parts.append(
                    f"- {seg_name}: {seg_data['count']} customers, "
                    f"avg revenue ${seg_data.get('avg_revenue', 0):,.0f}"
                )

            raw_context = "\n".join(context_parts)

            result_data = {
                "context": raw_context[:5000],
                "sources": [{"type": "odoo", "title": "Odoo CRM", "url": ""}],
                "crm_data": {
                    "customer_count": customer_count,
                    "opportunity_count": len(leads),
                    "order_count": len(orders),
                },
                "segments": list(segments.values()),
                "has_sufficient_data": has_sufficient_data,
            }

            # Cache the result
            await self.redis_manager.set_odoo_crm_cache(tenant_id, result_data)

            logger.info(
                "Extracted CRM data: %d customers, %d segments, sufficient=%s",
                customer_count,
                len(segments),
                has_sufficient_data,
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.warning("Odoo CRM extraction failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _segment_customers(
    customers: list[dict],
    leads: list[dict],
    orders: list[dict],
) -> dict[str, dict[str, Any]]:
    """Group customers by industry and compute segment metrics."""
    industry_groups: dict[str, list[dict]] = defaultdict(list)
    country_groups: dict[str, int] = defaultdict(int)

    for cust in customers:
        industry = cust.get("industry_id")
        if isinstance(industry, (list, tuple)) and len(industry) >= 2:
            industry_name = industry[1]
        else:
            industry_name = "Other"
        industry_groups[industry_name].append(cust)

        country = cust.get("country_id")
        if isinstance(country, (list, tuple)) and len(country) >= 2:
            country_groups[country[1]] += 1

    # Map partner_id -> revenue from orders
    partner_revenue: dict[int, float] = defaultdict(float)
    for order in orders:
        pid = order.get("partner_id")
        if isinstance(pid, (list, tuple)) and pid:
            partner_revenue[pid[0]] += order.get("amount_total", 0)

    # Build lead counts per partner
    partner_leads: dict[int, int] = defaultdict(int)
    partner_won: dict[int, int] = defaultdict(int)
    for lead in leads:
        pid = lead.get("partner_id")
        if isinstance(pid, (list, tuple)) and pid:
            partner_leads[pid[0]] += 1
            stage = lead.get("stage_id")
            if isinstance(stage, (list, tuple)) and stage:
                stage_name = str(stage[1]).lower()
                if "won" in stage_name or "closed" in stage_name:
                    partner_won[pid[0]] += 1

    segments: dict[str, dict[str, Any]] = {}
    for industry_name, custs in industry_groups.items():
        cust_ids = [c["id"] for c in custs]
        total_revenue = sum(partner_revenue.get(cid, 0) for cid in cust_ids)
        total_leads = sum(partner_leads.get(cid, 0) for cid in cust_ids)
        total_won = sum(partner_won.get(cid, 0) for cid in cust_ids)
        win_rate = (total_won / total_leads * 100) if total_leads > 0 else 0

        segments[industry_name] = {
            "name": industry_name,
            "count": len(custs),
            "total_revenue": round(total_revenue, 2),
            "avg_revenue": round(total_revenue / len(custs), 2) if custs else 0,
            "win_rate_pct": round(win_rate, 1),
            "top_countries": dict(
                sorted(country_groups.items(), key=lambda x: -x[1])[:5]
            ),
        }

    return segments


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
