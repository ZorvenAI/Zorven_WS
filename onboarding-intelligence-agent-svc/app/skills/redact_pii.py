"""SKL-OIA-16 — Redact PII from transcript text before buffering.

Design §8.1, §4.3 · implemented by story F-05.

Two entry points, one engine:

- ``redact_text()`` — called directly by the live audio pipeline. The
  pipeline needs the same transform without the full ``SkillContext``
  ceremony, so this is a plain function, not a method on the skill.
- ``RedactPii.run()`` — called through the skill registry / guardrail
  chain (IG-04). Wraps ``redact_text()`` so the registry path and the
  direct path use the same code.

The Presidio ``AnalyzerEngine`` is loaded once at first use and held for
the process lifetime. Pattern-based recognizers only (phone, email,
credit card, SSN) — no spaCy or NER model required. §8.3 requires
<200 ms per segment; the pattern-only engine typically runs in <5 ms.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)

_DEFAULT_ENTITIES = ["PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"]

_analyzer: Any = None
_anonymizer: Any = None
_ready = False


def _ensure_engines() -> bool:
    """Create the Presidio engines once. Returns True when available."""
    global _analyzer, _anonymizer, _ready
    if _ready:
        return _analyzer is not None
    _ready = True

    try:
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine
        from presidio_anonymizer import AnonymizerEngine

        class _PatternNlpEngine(NlpEngine):
            """Satisfies the Presidio interface without spaCy.

            Pattern recognizers (phone, email, credit card, SSN) need no NLP
            features — they match regex. This engine provides the empty
            artifacts the pipeline requires so those recognizers work without
            a 40 MB spaCy model download.
            """

            engine_name = "pattern"

            def process_text(self, text: str, language: str) -> NlpArtifacts:
                return NlpArtifacts(
                    entities=[],
                    tokens=[],
                    lemmas=[],
                    nlp_engine_name=self.engine_name,
                    language=language,
                )

            def process_batch(
                self, texts: Any, language: str, **kwargs: Any
            ) -> list[NlpArtifacts]:
                return [self.process_text(t, language) for t in texts]

            def is_loaded(self) -> bool:
                return True

        engine = _PatternNlpEngine()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=engine)
        _analyzer = AnalyzerEngine(
            nlp_engine=engine,
            registry=registry,
            supported_languages=["en"],
        )
        _anonymizer = AnonymizerEngine()
        logger.info("presidio_initialized")
        return True
    except Exception as exc:
        logger.warning("presidio_init_failed", error=str(exc))
        return False


def redact_text(
    text: str,
    *,
    entities: list[str] | None = None,
    language: str = "en",
) -> str:
    """Replace PII spans with ``<ENTITY_TYPE>`` placeholders.

    Returns the text unchanged when it contains no recognised PII.
    Falls back to regex patterns if Presidio is unavailable.
    """
    if not text or not text.strip():
        return text

    target = entities or _configured_entities()

    if not _ensure_engines() or _analyzer is None or _anonymizer is None:
        return _regex_fallback(text)

    results = _analyzer.analyze(text=text, entities=target, language=language)
    if not results:
        return text

    return _anonymizer.anonymize(text=text, analyzer_results=results).text


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


# ── IG-04 guardrail rule ───────────────────────────────────────────


def ig04_redact(payload: Any, context: SkillContext) -> Any:
    """IG-04 body: redact PII from the input before it reaches a skill."""
    from app.logic.guardrails import Action, Verdict

    if isinstance(payload, str):
        redacted = redact_text(payload)
        if redacted != payload:
            return Verdict(
                rule_id="IG-04",
                action=Action.REDACT,
                detail="PII redacted from input",
                payload=redacted,
            )
    return Verdict(rule_id="IG-04", action=Action.PASS, payload=payload)


# ── Skill wrapper ───────────────────────────────────────────────────


class RedactPii(BaseSkill):
    """SKL-OIA-16 — redact PII from transcript text."""

    async def run(self, context: SkillContext) -> SkillResult:
        text = context.input_prompt
        redacted = redact_text(text)
        return SkillResult(
            skill_id="SKL-OIA-16",
            output={"redacted_text": redacted, "redaction_applied": redacted != text},
        )
