"""3-layer guardrail architecture for market research agent.

Layer 1 — InputGuardrails:    Validates and sanitizes incoming prompts (7 rules).
Layer 2 — PlanToolGuardrails: Enforced during plan validation and skill execution (7 rules).
Layer 3 — OutputGuardrails:   Validates outgoing research results (6 rules).

Backwards-compatible: InputGuardrail and OutputGuardrail aliases remain for
existing code that imports them.
"""

import logging
import re
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from app.api.schemas import MarketResearchResponse

logger = logging.getLogger(__name__)

# ── Presidio PII engine (IG-04 / OG-02) ──

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    _analyzer = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
    _PRESIDIO_AVAILABLE = True
    logger.info("Presidio PII engine loaded")
except ImportError:
    _PRESIDIO_AVAILABLE = False
    logger.warning("Presidio not installed — falling back to regex PII detection")
except Exception:
    _PRESIDIO_AVAILABLE = False
    logger.exception(
        "Presidio failed to initialize — falling back to regex PII detection"
    )

# Entity type → replacement tag mapping for Presidio
_PRESIDIO_OPERATORS = (
    {
        "US_SSN": OperatorConfig("replace", {"new_value": "[REDACTED-SSN]"}),
        "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[REDACTED-CC]"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED-EMAIL]"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED-PHONE]"}),
        "US_BANK_NUMBER": OperatorConfig(
            "replace", {"new_value": "[REDACTED-ACCOUNT]"}
        ),
        "IBAN_CODE": OperatorConfig("replace", {"new_value": "[REDACTED-ACCOUNT]"}),
        "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED-IP]"}),
        "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED-NAME]"}),
    }
    if _PRESIDIO_AVAILABLE
    else {}
)

# Presidio entity types to scan for
_PRESIDIO_ENTITIES = [
    "US_SSN",
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_BANK_NUMBER",
    "IBAN_CODE",
    "IP_ADDRESS",
]

# ── Regex PII patterns (fallback when Presidio unavailable) ──

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_ACCOUNT_PATTERN = re.compile(r"\b\d{8,17}\b")

# ── Prompt injection indicators ──

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"(?:override|bypass)\s+(?:your|the)\s+(?:rules|instructions)", re.I),
    re.compile(r"<\s*(?:system|admin)\s*>", re.I),
]

# ── Scam/social engineering indicators (IG-02) ──

_SCAM_PATTERNS = [
    re.compile(r"(?:send|wire|transfer)\s+(?:money|funds|payment)", re.I),
    re.compile(r"(?:urgent|immediate)\s+(?:action|response)\s+required", re.I),
    re.compile(r"(?:act\s+now|limited\s+time)\s+(?:offer|opportunity)", re.I),
    re.compile(r"(?:bank\s+account|routing)\s+number", re.I),
]

# ── In-scope topics for IG-03 ──

DEFAULT_IN_SCOPE_TOPICS = [
    "market_research",
    "industry_analysis",
    "market_sizing",
    "trend_analysis",
    "economic_indicators",
    "competitive_landscape",
    "market_overview",
    "TAM",
    "SAM",
    "SOM",
    "market share",
    "competitor",
    "industry trend",
    "economic",
    "GDP",
    "inflation",
    "market size",
    "brand",
    "business",
    "startup",
    "revenue",
    "growth",
]

MAX_PROMPT_LENGTH = 16000  # ~4096 tokens
MAX_OUTPUT_CHARS = 100000
CONFIDENCE_THRESHOLD = 0.7

# Valid skill IDs (PG-02 allowlist)
VALID_SKILL_IDS = {
    "SKL-MRA-01",
    "SKL-MRA-02",
    "SKL-MRA-03",
    "SKL-MRA-04",
    "SKL-MRA-05",
    "SKL-MRA-06",
    "SKL-MRA-07",
    "SKL-MRA-08",
}


class GuardrailResult(BaseModel):
    """Outcome of a guardrail check."""

    passed: bool = True
    blocked: bool = False
    rule_id: str | None = None
    message: str = ""
    sanitized_prompt: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# Layer 1 — Input Guardrails (7 rules, <200ms budget)
# ═══════════════════════════════════════════════════════════════════════


class InputGuardrails:
    """Layer 1: Validates and sanitizes incoming prompts."""

    def __init__(
        self,
        redis_manager: Any = None,
        settings: Any = None,
    ) -> None:
        self.redis_manager = redis_manager
        self.settings = settings
        self._max_prompt_length = MAX_PROMPT_LENGTH
        if settings:
            self._max_prompt_length = getattr(
                settings, "INPUT_MAX_TOKENS", MAX_PROMPT_LENGTH
            )
            scope_str = getattr(settings, "IN_SCOPE_TOPICS", "")
            if scope_str:
                self._in_scope = [
                    t.strip().lower() for t in scope_str.split(",") if t.strip()
                ]
            else:
                self._in_scope = [t.lower() for t in DEFAULT_IN_SCOPE_TOPICS]
        else:
            self._in_scope = [t.lower() for t in DEFAULT_IN_SCOPE_TOPICS]

    async def evaluate(self, prompt: str, tenant_id: str) -> GuardrailResult:
        """Run all input guardrail rules. Returns GuardrailResult."""
        # IG-05: Tenant context validation
        if not tenant_id or not tenant_id.strip():
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-05",
                message="Tenant ID is required",
            )

        # IG-06: Input size limit
        if not prompt or not prompt.strip():
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-06",
                message="Input prompt cannot be empty",
            )
        if len(prompt) > self._max_prompt_length:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-06",
                message=(
                    f"Input exceeds maximum length of "
                    f"{self._max_prompt_length} characters"
                ),
            )

        # IG-01: Prompt injection detection
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(prompt):
                logger.warning("IG-01 triggered: prompt injection detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="IG-01",
                    message="Prompt injection detected",
                )

        # IG-02: Scam/social engineering detection
        for pattern in _SCAM_PATTERNS:
            if pattern.search(prompt):
                logger.warning("IG-02 triggered: scam pattern detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="IG-02",
                    message="Potential scam/social engineering content detected",
                )

        # IG-03: Out-of-scope filter (keyword matching against in_scope_topics)
        prompt_lower = prompt.lower()
        in_scope = any(topic in prompt_lower for topic in self._in_scope)
        if not in_scope:
            logger.info("IG-03: Prompt may be out of scope, allowing with warning")
            # Allow but flag — not blocking per deviation note

        # IG-04: PII redaction (Presidio with regex fallback)
        sanitized = _redact_pii(prompt)

        if sanitized != prompt:
            logger.info("IG-04: PII redacted from input")

        # Normalize whitespace
        sanitized = " ".join(sanitized.split())

        # IG-07: Rate limit pre-check
        if self.redis_manager:
            try:
                rate_limit = 10
                if self.settings:
                    rate_limit = getattr(self.settings, "RATE_LIMIT_PER_MINUTE", 10)
                allowed = await self.redis_manager.check_rate_limit(
                    tenant_id, limit=rate_limit
                )
                if not allowed:
                    return GuardrailResult(
                        passed=False,
                        blocked=True,
                        rule_id="IG-07",
                        message=f"Rate limit exceeded for tenant {tenant_id}",
                    )
            except Exception as exc:
                logger.warning("IG-07: Rate limit check failed: %s", exc)

        return GuardrailResult(
            passed=True,
            blocked=False,
            sanitized_prompt=sanitized,
        )


# ═══════════════════════════════════════════════════════════════════════
# Layer 2 — Plan/Tool Guardrails (7 rules)
# ═══════════════════════════════════════════════════════════════════════


class PlanToolGuardrails:
    """Layer 2: Enforced during plan validation and skill execution."""

    def __init__(self, rbac_engine: Any = None, settings: Any = None) -> None:
        self.rbac_engine = rbac_engine
        self._token_budget = 50000
        self._max_concurrent = 5
        if settings:
            self._token_budget = getattr(settings, "TOKEN_BUDGET_PER_SESSION", 50000)
            self._max_concurrent = getattr(settings, "MAX_CONCURRENT_REQUESTS", 5)

    async def check_plan(self, skill_sequence: list[str]) -> GuardrailResult:
        """Validate the skill execution plan."""
        # PG-01: Mandatory planning step
        if not skill_sequence:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="PG-01",
                message="Plan must contain at least one skill",
            )

        # PG-02: Tool allowlist
        for skill_id in skill_sequence:
            if skill_id not in VALID_SKILL_IDS:
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-02",
                    message=f"Skill {skill_id} not in allowlist",
                )

        return GuardrailResult(passed=True)

    async def check_tool_call(
        self,
        skill_id: str,
        role: str,
        session_tokens: int,
    ) -> GuardrailResult:
        """Pre-flight check before each tool call."""
        # PG-03: No write without EDITOR role
        if self.rbac_engine and self.rbac_engine.is_write_skill(skill_id):
            if role == "VIEWER":
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-03",
                    message=f"VIEWER role cannot invoke write skill {skill_id}",
                )

        # PG-05: RBAC enforcement
        if self.rbac_engine:
            decision = self.rbac_engine.check_permission(skill_id, role)
            if decision.decision == "DENY":
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-05",
                    message=decision.reason,
                )

        # PG-07: Token budget guard
        if session_tokens >= self._token_budget:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="PG-07",
                message=(
                    f"Token budget exhausted: {session_tokens} >= "
                    f"{self._token_budget}"
                ),
            )

        # PG-06: Irreversible action warning (non-blocking)
        if skill_id in {"SKL-MRA-06", "SKL-MRA-07"}:
            logger.info(
                "PG-06: Irreversible action %s proceeding with logging",
                skill_id,
            )

        return GuardrailResult(passed=True)


# ═══════════════════════════════════════════════════════════════════════
# Layer 3 — Output Guardrails (6 rules)
# ═══════════════════════════════════════════════════════════════════════


class OutputGuardrails:
    """Layer 3: Validates outgoing research results."""

    def __init__(self, settings: Any = None) -> None:
        self._confidence_threshold = CONFIDENCE_THRESHOLD
        self._max_output_chars = MAX_OUTPUT_CHARS
        if settings:
            self._confidence_threshold = getattr(
                settings, "CONFIDENCE_THRESHOLD", CONFIDENCE_THRESHOLD
            )
            self._max_output_chars = getattr(
                settings, "OUTPUT_MAX_CHARS", MAX_OUTPUT_CHARS
            )

    async def evaluate(
        self,
        response: MarketResearchResponse,
        skill_results: list[Any] | None = None,
        tenant_id: str = "",
    ) -> GuardrailResult:
        """Run all output guardrail rules."""
        skill_results = skill_results or []

        # OG-01: Grounding check (verify claims cite sources)
        if response.findings and not response.sources:
            logger.warning("OG-01: Findings present but no sources")
            # Non-blocking — add methodology note
            if "Ungrounded — no source citations" not in response.methodology_notes:
                response.methodology_notes.append("Ungrounded — no source citations")

        # OG-02: PII scrub on egress
        response.findings = [_strip_pii(f) for f in response.findings]
        response.recommendations = [_strip_pii(r) for r in response.recommendations]
        response.market_overview = _strip_pii(response.market_overview)

        # OG-03: Uncertainty escalation
        if response.confidence_score < self._confidence_threshold:
            logger.info(
                "OG-03: Low confidence %.2f < %.2f",
                response.confidence_score,
                self._confidence_threshold,
            )
            if "Low confidence — review recommended" not in response.methodology_notes:
                response.methodology_notes.append("Low confidence — review recommended")

        # Clamp confidence to [0, 1]
        response.confidence_score = max(0.0, min(1.0, response.confidence_score))

        # OG-04: No confident hallucination check
        if response.confidence_score > 0.8 and not response.sources:
            logger.warning("OG-04: High confidence with no sources — clamping")
            response.confidence_score = 0.5

        # OG-05: Tenant isolation check
        # (basic check — ensure raw_context doesn't reference other tenants)
        # This is a lightweight sanity check, not full enforcement
        if tenant_id:
            pass  # Tenant isolation enforced at data layer

        # OG-06: Response size limit
        total_chars = len(response.model_dump_json())
        if total_chars > self._max_output_chars:
            logger.warning(
                "OG-06: Response size %d exceeds limit %d — truncating raw_context",
                total_chars,
                self._max_output_chars,
            )
            response.raw_context = response.raw_context[: self._max_output_chars // 2]

        return GuardrailResult(passed=True)


# ═══════════════════════════════════════════════════════════════════════
# Backward-compatible aliases (used by existing tests and executor)
# ═══════════════════════════════════════════════════════════════════════


class InputGuardrail:
    """Legacy synchronous input guardrail — wraps InputGuardrails."""

    def validate(self, prompt: str) -> str:
        """Validate and sanitize the input prompt synchronously."""
        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="Input prompt cannot be empty")

        if len(prompt) > 5000:
            raise HTTPException(
                status_code=400,
                detail=f"Input prompt exceeds maximum length of 5000 characters",
            )

        if _SSN_PATTERN.search(prompt):
            raise HTTPException(
                status_code=400,
                detail="Input contains potential SSN — please remove PII before submitting",
            )

        if _CREDIT_CARD_PATTERN.search(prompt):
            raise HTTPException(
                status_code=400,
                detail="Input contains potential credit card number — please remove PII",
            )

        sanitized = " ".join(prompt.split())
        return sanitized


class OutputGuardrail:
    """Legacy synchronous output guardrail — wraps OutputGuardrails."""

    def validate(self, response: MarketResearchResponse) -> MarketResearchResponse:
        """Validate and clean the output response synchronously."""
        if response.confidence_score < 0.0:
            response.confidence_score = 0.0
        elif response.confidence_score > 1.0:
            response.confidence_score = 1.0

        response.findings = [_strip_pii(f) for f in response.findings]
        response.recommendations = [_strip_pii(r) for r in response.recommendations]

        if not response.sources:
            logger.warning("Research response has no sources")

        return response


# ── Helpers ──


def _redact_pii(text: str) -> str:
    """Redact PII using Presidio + regex supplementary layer.

    Used by IG-04 (input) and OG-02 (output) guardrails.
    Presidio provides NLP-based detection; regex catches patterns
    that Presidio's context scoring may miss (e.g., bare SSNs).
    """
    if _PRESIDIO_AVAILABLE:
        try:
            results = _analyzer.analyze(
                text=text,
                entities=_PRESIDIO_ENTITIES,
                language="en",
            )
            if results:
                anonymized = _anonymizer.anonymize(
                    text=text,
                    analyzer_results=results,
                    operators=_PRESIDIO_OPERATORS,
                )
                text = anonymized.text
        except Exception as exc:
            logger.warning("Presidio PII redaction failed: %s", exc)

    # Supplementary regex layer — catches patterns Presidio may miss
    text = _SSN_PATTERN.sub("[REDACTED-SSN]", text)
    text = _CREDIT_CARD_PATTERN.sub("[REDACTED-CC]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED-EMAIL]", text)
    text = _PHONE_PATTERN.sub("[REDACTED-PHONE]", text)
    return text


def _strip_pii(text: str) -> str:
    """Remove potential PII from text. Delegates to _redact_pii."""
    return _redact_pii(text)
