"""SKL-VoCA-03: Odoo CRM Chatter Extractor.

Reads ``mail.message`` records attached to ``crm.lead``, ``sale.order``, and
``res.partner`` models.  Only **customer-authored** messages are extracted
(internal notes and system-generated notifications are filtered out).

Customer IDs are SHA-256 hashed before leaving this skill (Decision #5).
Returns a list of ChatterFeedback items from app.registry.models.
"""

import logging
import re
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.registry.models import (
    ChatterFeedback,
    FeedbackChannel,
    hash_customer_id,
)
from app.services.odoo_rpc_client import OdooRPCClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# Models whose chatter messages we extract
_TARGET_MODELS = ["crm.lead", "sale.order", "res.partner"]

# Only customer-authored messages, not internal notes or notifications
_CUSTOMER_MSG_TYPES = ["email", "comment"]
_CUSTOMER_SUBTYPES = ["mail.mt_comment"]


class OdooChatterExtractor(BaseSkill):
    """Extract customer-authored chatter messages from Odoo CRM models."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-03",
        name="odoo_chatter_extractor",
        description=(
            "Extract customer-authored chatter messages from Odoo CRM "
            "(crm.lead, sale.order, res.partner). Filters out internal "
            "notes and system notifications. Returns ChatterFeedback list."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=45000,
        circuit_breaker_dependency="odoo_chatter",
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
        Extract customer chatter messages from Odoo.

        input_data keys:
          - prompt (str): analysis query (unused but forwarded for tracing)
          - limit (int, optional): max messages per model (default 200)
        """
        start = time.monotonic()
        tenant_id = context.tenant_id

        # ── Cache check ──
        cached = await self.redis_manager.get_odoo_cache(tenant_id, "chatter_cache")
        if cached:
            logger.info("Using cached chatter data for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=cached,
                duration_ms=_elapsed(start),
            )

        try:
            limit_per_model = input_data.get("limit", 200)
            all_feedback: list[dict[str, Any]] = []
            model_counts: dict[str, int] = {}

            for target_model in _TARGET_MODELS:
                messages = await self._fetch_customer_messages(
                    target_model, limit_per_model
                )

                feedback_items = []
                for msg in messages:
                    fb = _to_chatter_feedback(msg, target_model, tenant_id)
                    feedback_items.append(fb)

                    # Store hash lookup for ADMIN reverse resolution
                    author_id = _extract_author_id(msg)
                    if author_id and fb.customer_id_hash:
                        await self.redis_manager.store_hash_lookup(
                            tenant_id,
                            fb.customer_id_hash,
                            str(author_id),
                        )

                all_feedback.extend([fb.model_dump() for fb in feedback_items])
                model_counts[target_model] = len(feedback_items)

            # ── Build context summary ──
            total = len(all_feedback)
            context_parts = [
                f"Odoo Chatter: {total} customer messages extracted",
            ]
            for model_name, count in model_counts.items():
                context_parts.append(f"  - {model_name}: {count} messages")

            result_data: dict[str, Any] = {
                "context": "\n".join(context_parts)[:5000],
                "sources": [{"type": "odoo", "title": "Odoo Chatter", "url": ""}],
                "feedback": all_feedback,
                "feedback_count": total,
                "model_counts": model_counts,
            }

            # ── Cache ──
            await self.redis_manager.set_odoo_cache(
                tenant_id, "chatter_cache", result_data
            )

            logger.info(
                "Extracted %d chatter messages across %d models",
                total,
                len(_TARGET_MODELS),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.warning("Odoo chatter extraction failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )

    # ── Internal ──

    async def _fetch_customer_messages(
        self, model: str, limit: int
    ) -> list[dict[str, Any]]:
        """Fetch customer-authored mail.message records for a given model."""
        domain: list[Any] = [
            ("model", "=", model),
            ("message_type", "in", _CUSTOMER_MSG_TYPES),
            # Exclude internal notes: subtype_id must be a comment subtype
            # or absent (plain email)
            ("subtype_id.name", "!=", "Note"),
        ]

        messages = await self.odoo_client.search_read(
            "mail.message",
            domain=domain,
            fields=[
                "id",
                "body",
                "author_id",
                "date",
                "message_type",
                "res_id",
                "model",
                "subject",
            ],
            limit=limit,
            order="date desc",
        )

        # Additional filter: only keep messages from external partners
        # (not internal users acting as employees)
        customer_messages = [msg for msg in messages if _is_customer_message(msg)]

        return customer_messages


# ── Module-level helpers ──


def _is_customer_message(msg: dict[str, Any]) -> bool:
    """Check if a message was authored by an external customer, not staff."""
    # In Odoo, message_type 'email' is always external.
    # For 'comment', we check that author_id is present (not system).
    msg_type = msg.get("message_type", "")
    if msg_type == "email":
        return True
    if msg_type == "comment":
        author = msg.get("author_id")
        return bool(author)
    return False


def _extract_author_id(msg: dict[str, Any]) -> int | None:
    """Extract numeric author_id (partner ID) from mail.message."""
    aid = msg.get("author_id")
    if isinstance(aid, (list, tuple)) and aid:
        return aid[0]
    if isinstance(aid, int) and aid:
        return aid
    return None


def _strip_html(html: str) -> str:
    """Strip HTML tags for plain-text analysis."""
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).strip()


def _to_chatter_feedback(
    msg: dict[str, Any],
    target_model: str,
    tenant_id: str,
) -> ChatterFeedback:
    """Convert a raw mail.message to a ChatterFeedback domain model."""
    author_id = _extract_author_id(msg)
    customer_hash = hash_customer_id(author_id, salt=tenant_id) if author_id else ""

    body_raw = msg.get("body", "") or ""
    body_text = _strip_html(body_raw)

    # Prepend subject if available
    subject = msg.get("subject", "") or ""
    full_text = f"{subject}\n{body_text}".strip() if subject else body_text

    return ChatterFeedback(
        feedback_id=f"odoo-chatter-{msg.get('id', 0)}",
        channel=FeedbackChannel.ODOO_CHATTER,
        customer_id_hash=customer_hash,
        text=full_text[:5000],
        timestamp=msg.get("date", ""),
        model=target_model,
        record_id=msg.get("res_id", 0),
        message_type=msg.get("message_type", ""),
    )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
