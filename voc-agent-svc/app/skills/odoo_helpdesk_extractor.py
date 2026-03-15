"""SKL-VoCA-01: Odoo Helpdesk Ticket Extractor.

Extracts support tickets from Odoo Community (project.task) or Enterprise
(helpdesk.ticket).  The target model is auto-detected from a per-tenant
Redis config key ``tenant:<tid>:config.helpdesk_model`` and falls back to
``project.task`` when the key is absent (Community default).

Customer IDs are SHA-256 hashed before they leave this skill (Decision #5).
"""

import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.registry.models import (
    FeedbackChannel,
    TicketFeedback,
    hash_customer_id,
)
from app.services.odoo_rpc_client import OdooRPCClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# ── Defaults ──

_DEFAULT_MODEL = "project.task"
_ENTERPRISE_MODEL = "helpdesk.ticket"

# Fields common to both models
_COMMON_FIELDS = [
    "id",
    "name",
    "description",
    "partner_id",
    "priority",
    "stage_id",
    "create_date",
]

# Enterprise-only field
_ENTERPRISE_FIELDS = ["team_id"]


class OdooHelpdeskExtractor(BaseSkill):
    """Extract helpdesk / support tickets from Odoo for VoC analysis."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-01",
        name="odoo_helpdesk_extractor",
        description=(
            "Extract support tickets from Odoo (project.task for Community, "
            "helpdesk.ticket for Enterprise). Customer IDs are SHA-256 hashed. "
            "Returns TicketFeedback list for downstream theme clustering."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=45000,
        circuit_breaker_dependency="odoo_helpdesk",
    )

    def __init__(
        self,
        odoo_client: OdooRPCClient,
        redis_manager: RedisManager,
    ) -> None:
        self.odoo_client = odoo_client
        self.redis_manager = redis_manager

    # ── Execute ──

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Extract helpdesk tickets from Odoo.

        input_data keys:
          - prompt (str): analysis query (unused but forwarded for tracing)
          - limit (int, optional): max tickets to fetch (default 500)
        """
        start = time.monotonic()
        tenant_id = context.tenant_id

        # ── Cache check ──
        cached = await self.redis_manager.get_odoo_cache(tenant_id, "helpdesk_cache")
        if cached:
            logger.info("Using cached helpdesk data for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=cached,
                duration_ms=_elapsed(start),
            )

        try:
            # ── Detect model ──
            model = await self._resolve_model(tenant_id)
            is_enterprise = model == _ENTERPRISE_MODEL

            fields = list(_COMMON_FIELDS)
            if is_enterprise:
                fields.extend(_ENTERPRISE_FIELDS)

            limit = input_data.get("limit", 500)

            # ── Fetch tickets ──
            raw_tickets = await self.odoo_client.search_read(
                model,
                domain=[],
                fields=fields,
                limit=limit,
                order="create_date desc",
            )

            # ── Transform to TicketFeedback ──
            tickets: list[dict[str, Any]] = []
            for raw in raw_tickets:
                ticket = _to_ticket_feedback(raw, model, tenant_id)
                tickets.append(ticket.model_dump())

                # Store hash lookup for ADMIN reverse resolution
                partner_id = _extract_partner_id(raw)
                if partner_id:
                    await self.redis_manager.store_hash_lookup(
                        tenant_id,
                        ticket.customer_id_hash,
                        str(partner_id),
                    )

            # ── Build context summary ──
            context_parts = [
                f"Odoo Helpdesk ({model}): {len(tickets)} tickets extracted",
            ]
            priority_counts = _count_by_key(raw_tickets, "priority")
            for prio, count in sorted(priority_counts.items(), key=lambda x: -x[1]):
                context_parts.append(f"  - Priority {prio}: {count} tickets")

            result_data: dict[str, Any] = {
                "context": "\n".join(context_parts)[:5000],
                "sources": [{"type": "odoo", "title": f"Odoo {model}", "url": ""}],
                "tickets": tickets,
                "ticket_count": len(tickets),
                "model_used": model,
                "is_enterprise": is_enterprise,
            }

            # ── Cache ──
            await self.redis_manager.set_odoo_cache(
                tenant_id, "helpdesk_cache", result_data
            )

            logger.info(
                "Extracted %d helpdesk tickets from %s (enterprise=%s)",
                len(tickets),
                model,
                is_enterprise,
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.warning("Odoo helpdesk extraction failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )

    # ── Helpers ──

    async def _resolve_model(self, tenant_id: str) -> str:
        """Auto-detect helpdesk model from tenant config in Redis."""
        configured = await self.redis_manager.get_tenant_config(
            tenant_id, "helpdesk_model"
        )
        if configured and configured in (_DEFAULT_MODEL, _ENTERPRISE_MODEL):
            logger.info("Tenant %s helpdesk model override: %s", tenant_id, configured)
            return configured
        return _DEFAULT_MODEL


# ── Module-level helpers ──


def _extract_partner_id(raw: dict[str, Any]) -> int | None:
    """Extract numeric partner_id from Odoo many2one tuple."""
    pid = raw.get("partner_id")
    if isinstance(pid, (list, tuple)) and pid:
        return pid[0]
    if isinstance(pid, int) and pid:
        return pid
    return None


def _to_ticket_feedback(
    raw: dict[str, Any],
    model: str,
    tenant_id: str,
) -> TicketFeedback:
    """Convert a raw Odoo record to a TicketFeedback domain model."""
    partner_id = _extract_partner_id(raw)
    customer_hash = hash_customer_id(partner_id, salt=tenant_id) if partner_id else ""

    # Extract stage name from many2one
    stage = raw.get("stage_id")
    stage_name = ""
    if isinstance(stage, (list, tuple)) and len(stage) >= 2:
        stage_name = str(stage[1])

    # Build category from team_id if Enterprise
    team = raw.get("team_id")
    category = ""
    if isinstance(team, (list, tuple)) and len(team) >= 2:
        category = str(team[1])

    description = raw.get("description") or ""
    # Odoo may return HTML — strip for plain-text analysis
    if isinstance(description, str) and "<" in description:
        import re

        description = re.sub(r"<[^>]+>", " ", description).strip()

    return TicketFeedback(
        feedback_id=f"odoo-ticket-{raw.get('id', 0)}",
        channel=FeedbackChannel.ODOO_HELPDESK,
        customer_id_hash=customer_hash,
        text=description[:5000],
        timestamp=raw.get("create_date", ""),
        metadata={
            "model": model,
            "ticket_name": raw.get("name", ""),
        },
        ticket_id=raw.get("id", 0),
        priority=str(raw.get("priority", "")),
        stage=stage_name,
        category=category,
    )


def _count_by_key(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Count records grouped by a string-coercible field."""
    counts: dict[str, int] = {}
    for rec in records:
        val = str(rec.get(key, "unset"))
        counts[val] = counts.get(val, 0) + 1
    return counts


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
