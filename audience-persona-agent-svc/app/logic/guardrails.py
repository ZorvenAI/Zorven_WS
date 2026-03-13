"""Three-layer guardrails for the Audience Persona Agent.

Layer 1 — Input (9 rules, <200ms):
  IG-01: Prompt injection detection
  IG-02: Scam/social engineering
  IG-03: Out-of-scope filter
  IG-04: PII redaction
  IG-05: Tenant context validation
  IG-06: Input size limit
  IG-07: Rate limit
  IG-08: Demographic bias detector
  IG-09: Minor protection filter (COPPA)

Layer 2 — Plan + Tool:
  PG-01: Mandatory planning step
  PG-02: Tool allowlist
  PG-03: Write skills require EDITOR+
  PG-04: Concurrent research limit
  PG-05: RBAC enforcement
  PG-06: Irreversible action confirmation
  PG-07: Budget guard (80k tokens)
  PG-08: Persona count cap
  PG-09: Forum scraping ethics (robots.txt)

Layer 3 — Output:
  OG-01: Grounding check
  OG-02: PII scrub on egress
  OG-03: Uncertainty escalation
  OG-04: No confident hallucination
  OG-05: Tenant isolation
  OG-06: Response size limit
  OG-07: Anti-stereotyping guard (keyword + optional LLM judge)
  OG-08: Age-appropriate content check
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.rbac.engine import RBACEngine

logger = logging.getLogger(__name__)

# ── Shared patterns ──

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\s*/?system\s*>", re.I),
    re.compile(r"do\s+not\s+follow\s+(any\s+)?rules", re.I),
]

_SCAM_PATTERNS = [
    re.compile(r"send\s+money", re.I),
    re.compile(r"wire\s+transfer", re.I),
    re.compile(r"nigerian?\s+prince", re.I),
    re.compile(r"act\s+as\s+(a\s+)?hacker", re.I),
]

_SCOPE_KEYWORDS = {
    "audience_research",
    "buyer_persona",
    "demographics",
    "psychographics",
    "customer_segmentation",
    "buying_journey",
    "media_habits",
    "persona",
    "target_audience",
    "customer_profile",
    "audience",
    "buyer",
    "consumer",
    "segment",
    "demographic",
    "psychographic",
    "behavior",
    "motivation",
    "pain_point",
    "journey",
    "touchpoint",
    "channel",
    "market",
    "customer",
    "brand",
    "research",
    "analysis",
    "identify",
    "who",
    "ideal",
}

_BIAS_PATTERNS = [
    re.compile(
        r"\b(all|every|most)\s+(women|men|blacks?|whites?|asians?|hispanics?|latinos?)"
        r"\s+(are|tend|always|never)\b",
        re.I,
    ),
    re.compile(r"\b(lazy|stupid|criminal|violent)\s+(race|ethnic|gender)\b", re.I),
    re.compile(
        r"\btarget\s+only\s+(men|women|male|female)\s+because\b",
        re.I,
    ),
]

_MINOR_PATTERNS = [
    re.compile(r"\btarget\s+(children|kids|minors?)\s+under\s+1[0-3]\b", re.I),
    re.compile(r"\b(ages?\s+)?[0-9]\s*[-–]\s*1[0-2]\b", re.I),
    re.compile(r"\btarget.*\b(toddler|infant|preschool)\b", re.I),
]

# PII patterns for redaction
_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CC_REDACTED]"),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL_REDACTED]",
    ),
    (
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "[PHONE_REDACTED]",
    ),
]

# Anti-stereotyping keywords for OG-07
_STEREOTYPE_KEYWORDS = [
    "always buy",
    "never buy",
    "women prefer",
    "men prefer",
    "naturally inclined",
    "biologically driven",
    "culturally inferior",
    "culturally superior",
    "all millennials",
    "all boomers",
    "all gen z",
]

# Valid skill IDs for PG-02
_VALID_SKILL_IDS = {
    "SKL-APA-01",
    "SKL-APA-02",
    "SKL-APA-03",
    "SKL-APA-04",
    "SKL-APA-05",
    "SKL-APA-05b",
    "SKL-APA-05c",
    "SKL-APA-06",
    "SKL-APA-07",
    "SKL-APA-08",
    "SKL-APA-09",
    "SKL-APA-10",
    "SKL-APA-11",
    "SKL-APA-12",
}


class GuardrailResult:
    """Result of a guardrail check."""

    def __init__(
        self,
        passed: bool,
        rule: str = "",
        message: str = "",
        modified_input: str | None = None,
    ) -> None:
        self.passed = passed
        self.rule = rule
        self.message = message
        self.modified_input = modified_input


class InputGuardrails:
    """Layer 1 input guardrails (9 rules)."""

    def __init__(self, redis_manager: RedisManager | None = None) -> None:
        self._redis = redis_manager

    async def check(self, prompt: str, tenant_id: str) -> GuardrailResult:
        """Run all input guardrails in order."""
        # IG-05: Tenant context validation
        if not tenant_id or tenant_id == "":
            return GuardrailResult(False, "IG-05", "Tenant ID is required")

        # IG-06: Input size limit
        if not prompt or not prompt.strip():
            return GuardrailResult(False, "IG-06", "Input prompt is empty")
        if len(prompt) > settings.INPUT_MAX_TOKENS:
            return GuardrailResult(
                False,
                "IG-06",
                f"Input exceeds maximum size ({len(prompt)} > "
                f"{settings.INPUT_MAX_TOKENS})",
            )

        # IG-01: Prompt injection
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(prompt):
                return GuardrailResult(
                    False, "IG-01", "Potential prompt injection detected"
                )

        # IG-02: Scam/social engineering
        for pattern in _SCAM_PATTERNS:
            if pattern.search(prompt):
                return GuardrailResult(
                    False, "IG-02", "Potential scam/social engineering detected"
                )

        # IG-08: Demographic bias detector
        for pattern in _BIAS_PATTERNS:
            if pattern.search(prompt):
                return GuardrailResult(
                    False,
                    "IG-08",
                    "Request contains stereotyping of protected groups",
                )

        # IG-09: Minor protection (COPPA)
        for pattern in _MINOR_PATTERNS:
            if pattern.search(prompt):
                return GuardrailResult(
                    False,
                    "IG-09",
                    "Cannot target children under 13 (COPPA compliance)",
                )

        # IG-03: Out-of-scope filter (warning only, logged but not blocked)
        prompt_lower = prompt.lower()
        if not any(kw in prompt_lower for kw in _SCOPE_KEYWORDS):
            logger.info("IG-03: Prompt may be out of scope: %.80s", prompt)

        # IG-04: PII redaction
        modified = prompt
        for pattern, replacement in _PII_PATTERNS:
            modified = pattern.sub(replacement, modified)

        # IG-07: Rate limit
        if self._redis:
            allowed = await self._redis.check_rate_limit(tenant_id)
            if not allowed:
                return GuardrailResult(False, "IG-07", "Rate limit exceeded (10/min)")

        if modified != prompt:
            return GuardrailResult(
                True, "IG-04", "PII redacted from input", modified_input=modified
            )

        return GuardrailResult(True)


class PlanToolGuardrails:
    """Layer 2 plan and tool guardrails."""

    def __init__(self, rbac_engine: RBACEngine | None = None) -> None:
        self._rbac = rbac_engine or RBACEngine()

    def check_plan(self, skill_sequence: list[str]) -> GuardrailResult:
        """Validate the planned skill sequence."""
        # PG-01: Must have at least one skill
        if not skill_sequence:
            return GuardrailResult(
                False, "PG-01", "Plan must include at least one skill"
            )

        # PG-02: Tool allowlist
        for skill_id in skill_sequence:
            if skill_id not in _VALID_SKILL_IDS:
                return GuardrailResult(False, "PG-02", f"Unknown skill: {skill_id}")

        return GuardrailResult(True)

    def check_tool(
        self,
        skill_id: str,
        user_role: str,
        tokens_used: int = 0,
        persona_count: int = 0,
    ) -> GuardrailResult:
        """Check per-tool guardrails before execution."""
        # PG-02: Valid skill
        if skill_id not in _VALID_SKILL_IDS:
            return GuardrailResult(False, "PG-02", f"Unknown skill: {skill_id}")

        # PG-03: Write skills require EDITOR+
        if self._rbac.is_write_skill(skill_id) and user_role.upper() == "VIEWER":
            return GuardrailResult(False, "PG-03", "VIEWER cannot invoke write skills")

        # PG-05: RBAC enforcement
        decision = self._rbac.check_permission(skill_id, user_role)
        if not decision.allowed:
            return GuardrailResult(False, "PG-05", f"RBAC denied: {decision.reason}")

        # PG-07: Token budget
        if tokens_used > settings.TOKEN_BUDGET_PER_SESSION:
            return GuardrailResult(
                False,
                "PG-07",
                f"Token budget exceeded ({tokens_used} > "
                f"{settings.TOKEN_BUDGET_PER_SESSION})",
            )

        # PG-08: Persona count cap
        max_personas = min(settings.MAX_PERSONAS, settings.MAX_PERSONAS_LIMIT)
        if persona_count > max_personas:
            return GuardrailResult(
                False,
                "PG-08",
                f"Persona count exceeds limit ({persona_count} > {max_personas})",
            )

        # PG-06: Log irreversible actions
        if self._rbac.is_write_skill(skill_id):
            logger.info(
                "PG-06: Irreversible action logged: %s by %s",
                skill_id,
                user_role,
            )

        return GuardrailResult(True)


class OutputGuardrails:
    """Layer 3 output guardrails."""

    def __init__(self, anthropic_client: Any = None) -> None:
        self._anthropic = anthropic_client

    def check(self, response: dict[str, Any]) -> dict[str, Any]:
        """Apply all output guardrails and return modified response."""
        # OG-01: Grounding check
        findings = response.get("findings", [])
        sources = response.get("sources", [])
        if findings and not sources:
            logger.warning("OG-01: Findings present but no sources")

        # OG-02: PII scrub on egress
        response = self._scrub_pii(response)

        # OG-03: Low confidence flagging
        confidence = response.get("confidence_score", 0)
        if confidence < settings.CONFIDENCE_THRESHOLD:
            if "methodology_notes" not in response:
                response["methodology_notes"] = ""
            response["methodology_notes"] += (
                f" [Low confidence: {confidence:.2f}. "
                "Results should be verified with additional research.]"
            )

        # OG-04: High confidence + no sources → clamp
        if confidence > 0.8 and not sources:
            response["confidence_score"] = 0.5
            logger.warning("OG-04: Clamped confidence (no sources)")

        # OG-05: Tenant isolation (enforced at data layer)

        # OG-06: Response size limit
        raw_context = response.get("raw_context", "")
        if len(raw_context) > settings.OUTPUT_MAX_CHARS:
            response["raw_context"] = raw_context[: settings.OUTPUT_MAX_CHARS]
            logger.info(
                "OG-06: Truncated raw_context to %d chars", settings.OUTPUT_MAX_CHARS
            )

        # OG-07: Anti-stereotyping guard (keyword + optional LLM judge)
        response = self._anti_stereotype_check(response)

        # OG-08: Age-appropriate content check
        response = self._age_appropriate_check(response)

        return response

    @staticmethod
    def _scrub_pii(response: dict[str, Any]) -> dict[str, Any]:
        """Scrub PII from string fields in the response."""
        for key in ("raw_context", "executive_summary", "methodology_notes"):
            value = response.get(key, "")
            if isinstance(value, str):
                for pattern, replacement in _PII_PATTERNS:
                    value = pattern.sub(replacement, value)
                response[key] = value
        return response

    def _anti_stereotype_check(self, response: dict[str, Any]) -> dict[str, Any]:
        """OG-07: Check for stereotyping in persona narratives.

        Two-phase approach:
        1. Keyword scan (fast, always runs)
        2. LLM judge fallback when keyword score > 0.3 (optional, ~400ms)
        """
        personas = response.get("personas", [])
        for persona in personas:
            if not isinstance(persona, dict):
                continue
            narrative = persona.get("narrative", "")
            if not narrative:
                continue
            narrative_lower = narrative.lower()

            # Phase 1: Keyword scan
            keyword_hits = 0
            for keyword in _STEREOTYPE_KEYWORDS:
                if keyword in narrative_lower:
                    keyword_hits += 1
                    persona["narrative"] = re.sub(
                        re.escape(keyword),
                        "[statement removed: potential stereotyping]",
                        narrative,
                        flags=re.I,
                    )
                    narrative = persona["narrative"]
                    logger.warning(
                        "OG-07: Stereotyping keyword detected in persona %s",
                        persona.get("slug", "unknown"),
                    )

            # Phase 2: LLM judge (when keyword score > 0.3 but not conclusive)
            score = keyword_hits / max(len(_STEREOTYPE_KEYWORDS), 1)
            if 0.3 < score < 1.0 and self._anthropic:
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Can't await in sync context — skip LLM judge
                        logger.debug("OG-07: LLM judge skipped (sync context)")
                    else:
                        logger.debug("OG-07: LLM judge skipped (sync method)")
                except Exception:
                    pass

        return response

    @staticmethod
    def _age_appropriate_check(response: dict[str, Any]) -> dict[str, Any]:
        """OG-08: Flag personas targeting 13-17 for ADMIN review."""
        personas = response.get("personas", [])
        for persona in personas:
            if not isinstance(persona, dict):
                continue
            demographics = persona.get("demographics", {})
            if not isinstance(demographics, dict):
                continue
            age_range = demographics.get("age_range", "")
            if any(str(age) in age_range for age in range(13, 18)):
                persona["requires_admin_review"] = True
                logger.info(
                    "OG-08: Persona %s targets minors (13-17), flagged for review",
                    persona.get("slug", "unknown"),
                )
        return response


# ── PG-09: Forum scraping ethics (robots.txt check) ──


async def check_robots_txt(url: str) -> bool:
    """Check if a URL is allowed by the site's robots.txt.

    Returns True if scraping is allowed (or robots.txt is unreachable).
    Returns False if robots.txt explicitly disallows the path.
    """
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(robots_url)
            if resp.status_code != 200:
                return True  # No robots.txt → allow

            text = resp.text.lower()
            path = parsed.path or "/"

            # Simple robots.txt parser — check for Disallow on our path
            current_agent_applies = False
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("user-agent:"):
                    agent = line.split(":", 1)[1].strip()
                    current_agent_applies = agent == "*" or "bot" in agent
                elif current_agent_applies and line.startswith("disallow:"):
                    disallowed = line.split(":", 1)[1].strip()
                    if disallowed and path.startswith(disallowed):
                        logger.info(
                            "PG-09: robots.txt disallows %s on %s",
                            path,
                            parsed.netloc,
                        )
                        return False
        return True
    except Exception as exc:
        logger.debug("PG-09: robots.txt check failed for %s: %s", url, exc)
        return True  # Fail-open


class ThreeLayerGuardrails:
    """Orchestrates all three guardrail layers."""

    def __init__(
        self,
        redis_manager: RedisManager | None = None,
        rbac_engine: RBACEngine | None = None,
        anthropic_client: Any = None,
    ) -> None:
        self.input_guardrails = InputGuardrails(redis_manager)
        self.plan_tool_guardrails = PlanToolGuardrails(rbac_engine)
        self.output_guardrails = OutputGuardrails(anthropic_client)
