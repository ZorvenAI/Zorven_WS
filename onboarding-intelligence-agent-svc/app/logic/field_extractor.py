"""J-03 — Per-page field extraction with grounding and protection.

Design §8.2 SKL-OIA-10, §9.3 PROCESS sequence.

Extracts Company fields from assembled evidence one wizard page at a time.
Every value must carry evidence references (OG-01); fields with EDITED or
CONFIRMED provenance are never overwritten (PG-06). A schema failure on
one page does not lose the others (AC-5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.api.schemas import PageExtractionResponse
from app.core.config import Settings
from app.core.logging import get_logger
from app.logic.evidence_assembler import EvidenceBlock
from app.logic.field_types import FIELD_TYPE_HINTS, KEY_FIELDS, WIZARD_PAGES
from app.logic.output_guardrails import redact_value, scan_for_foreign_tenant
from app.providers.llm import LLMProvider, LLMUnavailable

logger = get_logger(__name__)


class StepBudgetExceeded(Exception):
    """PG-02: the 40-step budget has been exhausted."""


@dataclass
class ExtractedField:
    """One field extracted by the LLM with its provenance."""

    field_name: str
    value: Any
    confidence: float
    evidence: list[dict[str, Any]]
    classification: str


@dataclass
class PageResult:
    """Extraction result for one wizard page."""

    page: int
    label: str
    fields: list[ExtractedField] = field(default_factory=list)
    dropped_ungrounded: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ExtractionResult:
    """Aggregated extraction results across all pages."""

    pages: list[PageResult] = field(default_factory=list)
    fields_written: list[dict[str, Any]] = field(default_factory=list)
    fields_skipped: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    steps_used: int = 0
    dropped_ungrounded_total: int = 0


class FieldExtractor:
    """Extract Company fields from evidence, one wizard page at a time."""

    def __init__(
        self,
        llm: LLMProvider,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._steps = 0
        self._max_steps = settings.EXTRACTION_MAX_STEPS
        self._retry_limit = settings.EXTRACTION_RETRY_LIMIT
        self._temperature = settings.EXTRACTION_TEMPERATURE

    async def extract_all(
        self,
        *,
        evidence_blocks: list[EvidenceBlock],
        existing_provenance: list[dict[str, Any]],
        valid_recording_ids: set[str] | None = None,
        valid_media_ids: set[str] | None = None,
        tenant_id: str | None = None,
    ) -> ExtractionResult:
        """Run extraction across all wizard pages."""
        evidence_text = self._build_evidence_text(evidence_blocks)
        if not evidence_text.strip():
            logger.warning("extraction_no_evidence")
            return ExtractionResult()

        protected = self._build_protected_set(existing_provenance)

        result = ExtractionResult()

        for page_num in sorted(WIZARD_PAGES):
            page_label, page_fields = WIZARD_PAGES[page_num]

            page_result = await self._extract_page(
                page_num=page_num,
                page_label=page_label,
                page_fields=page_fields,
                evidence_text=evidence_text,
            )

            grounded, dropped = self._apply_grounding(
                page_result.fields,
                valid_recording_ids=valid_recording_ids,
                valid_media_ids=valid_media_ids,
            )
            page_result.fields = grounded
            page_result.dropped_ungrounded = dropped
            result.dropped_ungrounded_total += len(dropped)

            writable, skipped, conflicts = self._check_protected(
                page_result.fields, protected
            )
            page_result.fields = writable
            result.fields_skipped.extend(skipped)
            result.conflicts.extend(conflicts)

            for f in writable:
                result.fields_written.append(
                    {
                        "model_name": "Company",
                        "field_name": f.field_name,
                        "value": f.value,
                        "confidence": f.confidence,
                        "classification": f.classification,
                        "evidence": f.evidence,
                    }
                )

            result.pages.append(page_result)

        # OG-02: egress redaction — sole defense for PROCESS mode
        # (IG-04 covers the PREP/LIVE chain path, not this one)
        self._apply_egress_redaction(result)

        # OG-05: cross-tenant isolation — sole defense for PROCESS mode
        if tenant_id:
            self._check_tenant_isolation(result, tenant_id)

        result.steps_used = self._steps
        return result

    async def _extract_page(
        self,
        *,
        page_num: int,
        page_label: str,
        page_fields: frozenset[str],
        evidence_text: str,
    ) -> PageResult:
        """One LLM call per page, with retry on schema failure."""
        prompt = self._build_prompt(page_label, page_fields, evidence_text)

        for attempt in range(1 + self._retry_limit):
            self._step()

            try:
                raw = await self._llm.generate(
                    prompt,
                    temperature=self._temperature,
                    model=self._settings.PROCESS_MODEL,
                )
            except LLMUnavailable as exc:
                logger.error(
                    "extraction_llm_unavailable",
                    page=page_num,
                    error=str(exc),
                )
                return PageResult(
                    page=page_num,
                    label=page_label,
                    error=f"LLM unavailable: {exc}",
                )

            fields = self._parse_response(raw, page_fields)
            if fields is not None:
                return PageResult(
                    page=page_num,
                    label=page_label,
                    fields=fields,
                )

            if attempt < self._retry_limit:
                logger.warning(
                    "extraction_schema_retry",
                    page=page_num,
                    attempt=attempt + 1,
                )

        logger.error(
            "extraction_schema_failed",
            page=page_num,
            detail="dropped after retries",
        )
        return PageResult(
            page=page_num,
            label=page_label,
            error="schema validation failed after retries",
        )

    def _step(self) -> None:
        """Increment and enforce PG-02 step budget."""
        self._steps += 1
        if self._steps > self._max_steps:
            raise StepBudgetExceeded(
                f"PG-02: step budget {self._max_steps} exceeded "
                f"at step {self._steps}"
            )

    def _build_prompt(
        self,
        page_label: str,
        page_fields: frozenset[str],
        evidence_text: str,
    ) -> str:
        """Construct the extraction prompt for one wizard page."""
        field_descriptions: list[str] = []
        for name in sorted(page_fields):
            hint = FIELD_TYPE_HINTS.get(name, "string")
            field_descriptions.append(f"  - {name}: {hint}")

        fields_block = "\n".join(field_descriptions)

        return (
            "You are extracting structured company information from "
            "onboarding meeting evidence. Extract ONLY the fields listed "
            "below for the given wizard page. Do NOT invent information — "
            "every value must be directly supported by the evidence.\n\n"
            f"## Wizard Page: {page_label}\n\n"
            f"### Fields to extract:\n{fields_block}\n\n"
            "### Evidence:\n"
            f"{evidence_text}\n\n"
            "### Instructions:\n"
            "1. For each field, extract the value ONLY if the evidence "
            "directly supports it.\n"
            "2. Every field MUST include evidence references pointing to "
            "the source — either {recording_id, t_start, t_end} for "
            "transcript spans or {media_id} for media OCR.\n"
            "3. Set confidence between 0.0 and 1.0 based on how clearly "
            "the evidence supports the value.\n"
            "4. For JSON-typed fields (arrays, objects), return the value "
            "in the specified shape.\n"
            "5. Omit fields where the evidence is insufficient.\n\n"
            "Return ONLY valid JSON in this exact format:\n"
            "```json\n"
            '{"fields": [\n'
            '  {"field_name": "...", "value": ..., "confidence": 0.95, '
            '"evidence": [{"recording_id": "...", "t_start": 12.5, '
            '"t_end": 18.3}]}\n'
            "]}\n"
            "```\n"
        )

    def _parse_response(
        self,
        raw: str,
        page_fields: frozenset[str],
    ) -> list[ExtractedField] | None:
        """Parse LLM JSON response. Returns None on schema failure."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            parsed = PageExtractionResponse.model_validate_json(text)
        except Exception:
            try:
                data = json.loads(text)
                parsed = PageExtractionResponse.model_validate(data)
            except Exception:
                logger.warning(
                    "extraction_parse_failed",
                    raw_length=len(raw),
                )
                return None

        result: list[ExtractedField] = []
        for candidate in parsed.fields:
            if candidate.field_name not in page_fields:
                logger.warning(
                    "extraction_unknown_field",
                    field=candidate.field_name,
                )
                continue

            evidence_dicts: list[dict[str, Any]] = []
            for ref in candidate.evidence:
                evidence_dicts.append(ref.model_dump(exclude_none=True))

            result.append(
                ExtractedField(
                    field_name=candidate.field_name,
                    value=candidate.value,
                    confidence=candidate.confidence,
                    evidence=evidence_dicts,
                    classification=self._classify_field(
                        candidate.field_name, candidate.confidence
                    ),
                )
            )

        return result

    @staticmethod
    def _apply_grounding(
        candidates: list[ExtractedField],
        valid_recording_ids: set[str] | None = None,
        valid_media_ids: set[str] | None = None,
    ) -> tuple[list[ExtractedField], list[str]]:
        """OG-01: drop values whose evidence does not resolve.

        J-04 upgrade: when valid ID sets are provided, each evidence ref
        is checked against them. A hallucinated recording_id with plausible
        timestamps is dropped, not just an empty evidence list.
        """
        grounded: list[ExtractedField] = []
        dropped: list[str] = []

        for f in candidates:
            if not f.evidence:
                dropped.append(f.field_name)
                logger.info(
                    "og01_grounding_drop",
                    field=f.field_name,
                    detail="no evidence references",
                )
                continue

            if valid_recording_ids is None and valid_media_ids is None:
                grounded.append(f)
                continue

            resolved_refs: list[dict[str, Any]] = []
            for ref in f.evidence:
                rec_id = ref.get("recording_id")
                med_id = ref.get("media_id")

                if not rec_id and not med_id:
                    logger.info(
                        "og01_ref_unresolved",
                        field=f.field_name,
                        detail="ref has no verifiable identifiers",
                    )
                    continue

                rec_ok = (
                    rec_id in valid_recording_ids
                    if rec_id and valid_recording_ids is not None
                    else False
                )
                med_ok = (
                    med_id in valid_media_ids
                    if med_id and valid_media_ids is not None
                    else False
                )

                if not rec_ok and not med_ok:
                    logger.info(
                        "og01_ref_unresolved",
                        field=f.field_name,
                        recording_id=rec_id,
                        media_id=med_id,
                        detail="no ID resolved against session evidence",
                    )
                    continue

                resolved_refs.append(ref)

            if not resolved_refs:
                dropped.append(f.field_name)
                logger.info(
                    "og01_grounding_drop",
                    field=f.field_name,
                    detail="all evidence refs failed resolution",
                )
                continue

            f.evidence = resolved_refs
            grounded.append(f)

        return grounded, dropped

    @staticmethod
    def _check_protected(
        candidates: list[ExtractedField],
        protected: dict[str, dict[str, Any]],
    ) -> tuple[
        list[ExtractedField],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """PG-06: skip EDITED/CONFIRMED fields, report conflicts."""
        writable: list[ExtractedField] = []
        skipped: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        for f in candidates:
            key = f"Company.{f.field_name}"
            existing = protected.get(key)

            if existing is None:
                writable.append(f)
                continue

            conflicts.append(
                {
                    "field_name": f.field_name,
                    "existing_status": existing["status"],
                    "existing_value": existing.get("extracted_value"),
                    "new_value": f.value,
                    "new_evidence": f.evidence,
                    "new_confidence": f.confidence,
                    "new_classification": f.classification,
                    "existing_source_span": existing.get("source_span"),
                    "existing_confidence": existing.get("confidence"),
                }
            )
            skipped.append(
                {
                    "field_name": f.field_name,
                    "reason": "protected",
                    "status": existing["status"],
                }
            )
            logger.info(
                "pg06_protected_skip",
                field=f.field_name,
                status=existing["status"],
            )

        return writable, skipped, conflicts

    @staticmethod
    def _build_protected_set(
        existing_provenance: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build a lookup of protected provenance records."""
        protected: dict[str, dict[str, Any]] = {}
        for p in existing_provenance:
            status = p.get("status", "")
            if status in ("CONFIRMED", "EDITED"):
                key = f"{p.get('model_name', '')}.{p.get('field_name', '')}"
                protected[key] = p
        return protected

    def _classify_field(self, field_name: str, confidence: float = 1.0) -> str:
        """OG-03: KEY fields gate review, SECONDARY do not.

        J-04: confidence below threshold forces KEY regardless of field name,
        ensuring uncertain values go through mandatory review.
        """
        threshold = self._settings.OG03_KEY_CONFIDENCE_THRESHOLD
        if confidence < threshold:
            logger.info(
                "og03_confidence_key_forcing",
                field=field_name,
                confidence=confidence,
                threshold=threshold,
            )
            return "KEY"
        return "KEY" if field_name in KEY_FIELDS else "SECONDARY"

    @staticmethod
    def _apply_egress_redaction(result: "ExtractionResult") -> None:
        """OG-02: re-apply PII redaction on egress values."""
        for entry in result.fields_written:
            value = entry.get("value")
            new_value, changed = redact_value(value)
            if changed:
                logger.info(
                    "og02_egress_redaction",
                    field=entry.get("field_name"),
                )
                entry["value"] = new_value

    @staticmethod
    def _check_tenant_isolation(result: "ExtractionResult", tenant_id: str) -> None:
        """OG-05: cross-tenant identifier in output → security BLOCK."""
        from app.logic.guardrails import Action, GuardrailViolation, Verdict

        for entry in result.fields_written:
            value = entry.get("value")
            foreign = scan_for_foreign_tenant(value, tenant_id)
            if foreign is not None:
                logger.error(
                    "og05_cross_tenant_block",
                    field=entry.get("field_name"),
                    foreign_tenant_id=foreign,
                    detail="cross-tenant identifier in extraction output",
                )
                raise GuardrailViolation(
                    Verdict(
                        rule_id="OG-05",
                        action=Action.BLOCK,
                        detail=(
                            f"cross-tenant identifier {foreign} found in "
                            f"field {entry.get('field_name')}"
                        ),
                    )
                )

    @staticmethod
    def _build_evidence_text(blocks: list[EvidenceBlock]) -> str:
        """Format evidence blocks for the extraction prompt."""
        parts: list[str] = []

        for i, block in enumerate(blocks):
            header = f"[Evidence {i + 1} — {block.source_type}"
            if block.recording_id:
                header += f", recording={block.recording_id}"
            if block.media_id:
                header += f", media={block.media_id}"
            header += "]"

            span_info = ""
            if block.spans:
                spans_str = ", ".join(
                    f"{{recording_id: {s.recording_id}, "
                    f"t_start: {s.t_start}, t_end: {s.t_end}}}"
                    for s in block.spans
                )
                span_info = f"\nSpans: [{spans_str}]"

            parts.append(f"{header}{span_info}\n{block.text}")

        return "\n\n---\n\n".join(parts)
