"""SKL-VoCA-04: Odoo Customer Segment Linker.

Links feedback ``partner_id`` (hashed) to APA persona segments by reading
``previous_outputs["audience_persona"]`` from the pipeline context.

Operates entirely in-memory — no Odoo RPC calls are made. In **External-Only
Mode** (when Odoo data is unavailable), the linker produces inferred mappings
with lower confidence scores.

Returns a list of LinkedFeedback items from app.registry.models.
"""

import logging
import time
from typing import Any

from app.registry.models import LinkedFeedback
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# Confidence levels for different linking methods
_CONFIDENCE_DIRECT_MATCH = 0.95
_CONFIDENCE_SEGMENT_MATCH = 0.80
_CONFIDENCE_INFERRED = 0.45


class OdooCustomerSegmentLinker(BaseSkill):
    """Link feedback to APA persona segments using in-memory mapping."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-04",
        name="odoo_customer_segment_linker",
        description=(
            "Link feedback partner_id (hashed) to APA persona segments "
            "from previous_outputs.audience_persona. In-memory mapping, "
            "no Odoo calls. Lower confidence in External-Only Mode."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        idempotent=True,
        timeout_ms=15000,
        circuit_breaker_dependency="",
    )

    # ── Execute ──

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Link feedback items to persona segments.

        input_data keys:
          - feedback (list[dict]): feedback items with customer_id_hash
          - prompt (str, optional): analysis query (unused)

        context keys used:
          - previous_outputs["audience_persona"]: APA personas with segments
          - operating_mode: "full" or "external_only"
        """
        start = time.monotonic()

        try:
            feedback_items = input_data.get("feedback", [])
            if not feedback_items:
                logger.info("No feedback items to link")
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    success=True,
                    data={
                        "context": "No feedback items provided for linking",
                        "linked_feedback": [],
                        "linked_count": 0,
                        "unlinked_count": 0,
                        "link_rate": 0.0,
                    },
                    duration_ms=_elapsed(start),
                )

            # ── Extract APA persona data ──
            apa_data = context.previous_outputs.get("audience_persona", {})
            is_external_only = context.operating_mode == "external_only"

            # Build the mapping index
            segment_map = _build_segment_map(apa_data)

            # ── Link feedback ──
            linked: list[dict[str, Any]] = []
            unlinked_count = 0

            for item in feedback_items:
                customer_hash = item.get("customer_id_hash", "")
                feedback_id = item.get("feedback_id", "")

                if not feedback_id:
                    continue

                link = _link_feedback_item(
                    feedback_id=feedback_id,
                    customer_hash=customer_hash,
                    segment_map=segment_map,
                    is_external_only=is_external_only,
                    feedback_metadata=item.get("metadata", {}),
                )

                if link:
                    linked.append(link.model_dump())
                else:
                    unlinked_count += 1

            # ── Compute statistics ──
            total = len(linked) + unlinked_count
            link_rate = (len(linked) / total * 100) if total > 0 else 0.0

            # ── Context summary ──
            context_parts = [
                f"Segment Linking: {len(linked)}/{total} feedback items linked "
                f"({link_rate:.1f}%)",
                f"Personas available: {len(segment_map.get('personas', {}))}",
                f"Mode: {'external_only (inferred)' if is_external_only else 'full (direct)'}",
            ]

            # Breakdown by persona
            persona_counts: dict[str, int] = {}
            for lf in linked:
                slug = lf.get("persona_slug", "unknown")
                persona_counts[slug] = persona_counts.get(slug, 0) + 1
            for slug, count in sorted(persona_counts.items(), key=lambda x: -x[1]):
                context_parts.append(f"  - {slug}: {count} items")

            result_data: dict[str, Any] = {
                "context": "\n".join(context_parts)[:5000],
                "sources": [
                    {
                        "type": "apa_pipeline",
                        "title": "APA Persona Segments",
                        "url": "",
                    }
                ],
                "linked_feedback": linked,
                "linked_count": len(linked),
                "unlinked_count": unlinked_count,
                "link_rate": round(link_rate, 2),
                "is_external_only": is_external_only,
                "persona_distribution": persona_counts,
            }

            logger.info(
                "Linked %d/%d feedback items (%.1f%%), mode=%s",
                len(linked),
                total,
                link_rate,
                "external_only" if is_external_only else "full",
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.warning("Customer segment linking failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


# ── Module-level helpers ──


def _build_segment_map(apa_data: dict[str, Any]) -> dict[str, Any]:
    """Build lookup structures from APA persona output.

    Expected APA data shapes:
      - personas: list of dicts with slug, customer_id_hashes, industries,
        company_sizes, etc.
      - segments: list of dicts with segment info and partner mappings
    """
    segment_map: dict[str, Any] = {
        "hash_to_persona": {},  # customer_id_hash -> persona_slug
        "industry_to_persona": {},  # industry -> persona_slug
        "personas": {},  # slug -> persona dict
    }

    if not apa_data:
        return segment_map

    # Extract personas from various possible APA output shapes
    personas = apa_data.get("personas", [])
    if isinstance(personas, dict):
        personas = list(personas.values())

    for persona in personas:
        if not isinstance(persona, dict):
            continue

        slug = persona.get("persona_slug", "") or persona.get("slug", "")
        if not slug:
            continue

        segment_map["personas"][slug] = persona

        # Map customer hashes to persona (direct CRM-grounded link)
        for cid_hash in persona.get("customer_id_hashes", []):
            segment_map["hash_to_persona"][cid_hash] = slug

        # Map industries to persona (for inferred linking)
        for industry in persona.get("industries", []):
            if isinstance(industry, str) and industry:
                segment_map["industry_to_persona"][industry.lower()] = slug

    return segment_map


def _link_feedback_item(
    feedback_id: str,
    customer_hash: str,
    segment_map: dict[str, Any],
    is_external_only: bool,
    feedback_metadata: dict[str, Any],
) -> LinkedFeedback | None:
    """Attempt to link a single feedback item to a persona.

    Linking priority:
    1. Direct hash match (highest confidence)
    2. Industry/segment match (medium confidence)
    3. Inferred mapping in external-only mode (lower confidence)
    """
    hash_to_persona = segment_map.get("hash_to_persona", {})
    industry_to_persona = segment_map.get("industry_to_persona", {})
    personas = segment_map.get("personas", {})

    # If no personas available, cannot link
    if not personas:
        return None

    # ── 1. Direct hash match ──
    if customer_hash and customer_hash in hash_to_persona:
        return LinkedFeedback(
            feedback_id=feedback_id,
            persona_slug=hash_to_persona[customer_hash],
            confidence=_CONFIDENCE_DIRECT_MATCH,
            linking_method="direct_hash_match",
        )

    # ── 2. Industry/metadata-based match ──
    industry = feedback_metadata.get("industry", "")
    if industry and industry.lower() in industry_to_persona:
        return LinkedFeedback(
            feedback_id=feedback_id,
            persona_slug=industry_to_persona[industry.lower()],
            confidence=_CONFIDENCE_SEGMENT_MATCH,
            linking_method="industry_segment_match",
        )

    # ── 3. Inferred match (External-Only Mode) ──
    if is_external_only and personas:
        # In external-only mode, assign to the most common persona
        # with lower confidence as a best-effort mapping
        default_slug = next(iter(personas))
        return LinkedFeedback(
            feedback_id=feedback_id,
            persona_slug=default_slug,
            confidence=_CONFIDENCE_INFERRED,
            linking_method="inferred_external_only",
        )

    return None


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
