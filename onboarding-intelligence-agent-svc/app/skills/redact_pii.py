"""SKL-OIA-16 — Redact PII from transcript text before buffering.

Design §8.1, §4.3, §5.1 IG-04 · implemented by F-05, upgraded by G-01.

Two entry points, one engine:

- ``redact_text()`` — called directly by the live audio pipeline. The
  pipeline needs the same transform without the full ``SkillContext``
  ceremony, so this is a plain function, not a method on the skill.
- ``RedactPii.run()`` — called through the skill registry / guardrail
  chain (IG-04). Wraps ``redact_text()`` so the registry path and the
  direct path use the same code.

G-01 replaces the F-05 pattern-only engine with spaCy NER, enabling
PERSON and LOCATION detection. The analyser is loaded once at first use.
§8.3 requires <200 ms per segment; spaCy ``en_core_web_sm`` typically
runs in <5 ms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)

_DEFAULT_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_SSN",
    "US_ITIN",
    "LOCATION",
]

_analyzer: Any = None
_anonymizer: Any = None
_ready = False


@dataclass
class RedactionResult:
    """What ``redact_text`` returns — text plus metadata for EVT-103."""

    text: str
    applied: bool
    entity_types: list[str] = field(default_factory=list)


def _ensure_engines() -> bool:
    """Create the Presidio engines once. Returns True when available.

    G-01 replaces the F-05 ``_PatternNlpEngine`` with Presidio's default
    ``AnalyzerEngine()``, which auto-detects spaCy when ``en_core_web_sm``
    is installed. This enables PERSON and LOCATION detection via NER.

    Falls back to pattern-only recognition when spaCy is unavailable.
    """
    global _analyzer, _anonymizer, _ready
    if _ready:
        return _analyzer is not None

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()  # type: ignore[no-untyped-call]
        _ready = True
        logger.info("presidio_initialized", ner_available=True)
        return True
    except Exception as exc:
        logger.warning("presidio_init_failed", error=str(exc))
        return False


def _is_allowlisted(matched_text: str, allowlist: list[str]) -> bool:
    """Check whether detected text should be kept (not redacted).

    AC-3: business identity is not collateral damage. A brand name like
    "Kelso Coffee" or a person-like name like "Marlow & Sons" must survive
    when it appears in the allowlist.

    Two checks: exact match (case-insensitive) and containment — "Kelso"
    detected inside "Kelso Coffee" is allowlisted because the operator
    named the business, not the person.
    """
    lower = matched_text.lower().strip()
    if not lower:
        return False
    for term in allowlist:
        term_lower = term.lower().strip()
        if not term_lower:
            continue
        if lower == term_lower:
            return True
        if lower in term_lower or term_lower in lower:
            return True
    return False


def redact_text(
    text: str,
    *,
    entities: list[str] | None = None,
    language: str = "en",
    allowlist: list[str] | None = None,
) -> RedactionResult:
    """Replace PII spans with ``<ENTITY_TYPE>`` placeholders.

    Returns a ``RedactionResult`` with the redacted text, whether any PII
    was found, and which entity types were detected (for EVT-103).

    Falls back to regex patterns if Presidio is unavailable.
    """
    if not text or not text.strip():
        return RedactionResult(text=text, applied=False)

    target = entities or _configured_entities()
    safe_allowlist = allowlist or []

    if not _ensure_engines() or _analyzer is None or _anonymizer is None:
        fallback = _regex_fallback(text)
        return RedactionResult(
            text=fallback,
            applied=fallback != text,
            entity_types=_regex_entity_types(text) if fallback != text else [],
        )

    results = _analyzer.analyze(text=text, entities=target, language=language)
    if not results:
        return RedactionResult(text=text, applied=False)

    if safe_allowlist:
        filtered = []
        for r in results:
            matched = text[r.start : r.end]
            if _is_allowlisted(matched, safe_allowlist):
                continue
            filtered.append(r)
        results = filtered

    if not results:
        return RedactionResult(text=text, applied=False)

    entity_types = sorted(set(r.entity_type for r in results))

    redacted = _anonymizer.anonymize(  # type: ignore[no-any-return]
        text=text,
        analyzer_results=results,
    ).text

    return RedactionResult(
        text=redacted,
        applied=True,
        entity_types=entity_types,
    )


def _configured_entities() -> list[str]:
    from app.core.config import get_settings

    raw = get_settings().PII_ENTITIES
    if not raw or not raw.strip():
        return list(_DEFAULT_ENTITIES)
    return [e.strip() for e in raw.split(",") if e.strip()]


# ── Regex fallback ──────────────────────────────────────────────────

_PHONE_RE = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def _regex_fallback(text: str) -> str:
    """Pattern-only redaction when Presidio is unavailable."""
    text = _SSN_RE.sub("<US_SSN>", text)
    text = _CC_RE.sub("<CREDIT_CARD>", text)
    text = _PHONE_RE.sub("<PHONE_NUMBER>", text)
    text = _EMAIL_RE.sub("<EMAIL_ADDRESS>", text)
    return text


def _regex_entity_types(text: str) -> list[str]:
    """Detect which entity types the regex fallback would find."""
    types: list[str] = []
    if _SSN_RE.search(text):
        types.append("US_SSN")
    if _CC_RE.search(text):
        types.append("CREDIT_CARD")
    if _PHONE_RE.search(text):
        types.append("PHONE_NUMBER")
    if _EMAIL_RE.search(text):
        types.append("EMAIL_ADDRESS")
    return sorted(types)


# ── IG-04 guardrail rule ───────────────────────────────────────────


def ig04_redact(payload: Any, context: SkillContext) -> Any:
    """IG-04 body: redact PII from the input before it reaches a skill."""
    from app.logic.guardrails import Action, Verdict

    if isinstance(payload, str):
        result = redact_text(payload)
        if result.applied:
            return Verdict(
                rule_id="IG-04",
                action=Action.REDACT,
                detail="PII redacted from input",
                payload=result.text,
            )
    return Verdict(rule_id="IG-04", action=Action.PASS, payload=payload)


# ── Skill wrapper ───────────────────────────────────────────────────


class RedactPii(BaseSkill):
    """SKL-OIA-16 — redact PII from transcript text."""

    async def run(self, context: SkillContext) -> SkillResult:
        text = context.input_prompt
        result = redact_text(text)
        return SkillResult(
            skill_id="SKL-OIA-16",
            output={
                "redacted_text": result.text,
                "redaction_applied": result.applied,
                "entity_types": result.entity_types,
            },
        )
