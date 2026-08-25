"""SKL-OIA-10 — Extract Company fields from evidence, page by page.

Design §8.2 · implemented by story J-03.

The core PROCESS skill. Maps all session evidence onto Company fields,
one wizard page at a time. Every value carries evidence references
(OG-01) and a KEY|SECONDARY classification (OG-03). Honours PG-06:
fields whose provenance is EDITED or CONFIRMED are never overwritten.
"""

from __future__ import annotations

from typing import Any

from app.logic.field_extractor import ExtractionResult, FieldExtractor
from app.providers.llm import LLMProvider
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult


class ExtractAndMapFields(BaseSkill):
    """Extract Company fields from the evidence set and map them."""

    def __init__(self, meta: Any, *, llm: LLMProvider | None = None) -> None:
        super().__init__(meta)
        self._llm = llm

    async def run(self, context: SkillContext) -> SkillResult:
        if self._llm is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={"error": "LLM provider not available"},
            )

        from app.core.config import get_settings

        settings = get_settings()
        extractor = FieldExtractor(llm=self._llm, settings=settings)

        evidence_blocks = context.input_context.get("evidence_blocks", [])
        existing_provenance = context.input_context.get("existing_provenance", [])

        result: ExtractionResult = await extractor.extract_all(
            evidence_blocks=evidence_blocks,
            existing_provenance=existing_provenance,
        )

        key_count = sum(
            1 for f in result.fields_written if f.get("classification") == "KEY"
        )
        secondary_count = sum(
            1 for f in result.fields_written if f.get("classification") == "SECONDARY"
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "fields_written": result.fields_written,
                "fields_skipped": result.fields_skipped,
                "conflicts": result.conflicts,
                "key_count": key_count,
                "secondary_count": secondary_count,
                "steps_used": result.steps_used,
                "dropped_ungrounded": result.dropped_ungrounded_total,
                "pages": [
                    {
                        "page": p.page,
                        "label": p.label,
                        "fields_count": len(p.fields),
                        "dropped_count": len(p.dropped_ungrounded),
                        "error": p.error,
                    }
                    for p in result.pages
                ],
            },
        )
