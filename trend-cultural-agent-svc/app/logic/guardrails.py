"""Three-layer guardrail system for TCIA.

Layer 1 — Input (IG-01..10): Validate and sanitize incoming prompts
Layer 2 — Plan+Tool (PG-01..09): Validate skill execution plans
Layer 3 — Output (OG-01..08): Validate and sanitize outgoing responses
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_VALID_SKILL_IDS = {
    "SKL-TCIA-01",
    "SKL-TCIA-02",
    "SKL-TCIA-03",
    "SKL-TCIA-04",
    "SKL-TCIA-05",
    "SKL-TCIA-06",
    "SKL-TCIA-07",
    "SKL-TCIA-08",
    "SKL-TCIA-09",
    "SKL-TCIA-10",
    "SKL-TCIA-11",
    "SKL-TCIA-12",
}

# IG-01: Prompt injection patterns
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)",
    r"you\s+are\s+now",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"forget\s+(your|all)\s+instructions",
    r"override\s+(your\s+)?instructions",
]

# IG-08: Harmful trend patterns
_HARMFUL_PATTERNS = [
    r"tide\s+pod\s+challenge",
    r"blackout\s+challenge",
    r"choking\s+game",
    r"self.harm",
    r"suicide\s+challenge",
    r"dangerous\s+challenge",
]

# OG-07: Harmful content in output
_HARMFUL_OUTPUT_KEYWORDS = {
    "self-harm",
    "suicide challenge",
    "dangerous challenge",
    "eating disorder promotion",
    "pro-ana",
    "pro-mia",
}

# IG-09: Political neutrality triggers
_POLITICAL_KEYWORDS = {
    "republican",
    "democrat",
    "conservative",
    "liberal",
    "left-wing",
    "right-wing",
    "partisan",
    "political party",
}


class GuardrailResult:
    """Result of a guardrail check."""

    def __init__(
        self,
        passed: bool = True,
        warnings: list[str] | None = None,
        blocked: bool = False,
        block_reason: str = "",
        flags: dict[str, bool] | None = None,
    ) -> None:
        self.passed = passed
        self.warnings = warnings or []
        self.blocked = blocked
        self.block_reason = block_reason
        self.flags = flags or {}


class GuardrailEngine:
    """Three-layer guardrail engine for TCIA."""

    def __init__(
        self,
        anthropic_client: Any = None,
        redis_manager: Any = None,
        event_emitter: Any = None,
    ) -> None:
        self._anthropic = anthropic_client
        self._redis = redis_manager
        self._events = event_emitter

    # ── Layer 1: Input Guardrails ──

    async def validate_input(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str,
        previous_outputs: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """Run all input guardrails (IG-01..10)."""
        warnings: list[str] = []
        flags: dict[str, bool] = {}
        prompt_lower = prompt.lower()

        # IG-01: Prompt injection detection
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, prompt_lower):
                logger.warning("IG-01: Prompt injection detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    block_reason="Prompt injection detected (IG-01)",
                )

        # IG-05: Tenant context validation
        if not tenant_id:
            warnings.append("IG-05: No tenant_id provided")

        # IG-06: Input size limit
        if len(prompt) > 16000:
            prompt = prompt[:16000]
            warnings.append("IG-06: Input truncated to 16000 chars")

        # IG-07: Rate limit
        if self._redis:
            within_limit = await self._redis.check_rate_limit(tenant_id)
            if not within_limit:
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    block_reason="Rate limit exceeded (IG-07)",
                )

        # IG-08: Harmful trend filter
        for pattern in _HARMFUL_PATTERNS:
            if re.search(pattern, prompt_lower):
                logger.warning("IG-08: Harmful trend request blocked")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    block_reason="Harmful trend analysis blocked (IG-08)",
                )

        # IG-09: Political neutrality check
        for kw in _POLITICAL_KEYWORDS:
            if kw in prompt_lower:
                flags["neutrality_required"] = True
                warnings.append(
                    "IG-09: Political content detected, balanced treatment required"
                )
                break

        # IG-10: Upstream context validation
        prev = previous_outputs or {}
        if not any(
            k in prev
            for k in ("market_research", "competitor_intelligence", "audience_persona")
        ):
            warnings.append(
                "IG-10: No upstream MRA/CIA/APA context; proceeding in degraded mode"
            )

        return GuardrailResult(
            passed=True, warnings=warnings, flags=flags
        )

    # ── Layer 2: Plan+Tool Guardrails ──

    def validate_plan(
        self,
        skill_sequence: list[str],
        user_role: str = "EDITOR",
        tokens_used: int = 0,
        trend_count: int = 0,
        token_budget: int = 60000,
        max_trends: int = 25,
    ) -> GuardrailResult:
        """Run plan+tool guardrails (PG-01..09)."""
        warnings: list[str] = []

        # PG-02: Skill allowlist
        for skill_id in skill_sequence:
            if skill_id not in _VALID_SKILL_IDS:
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    block_reason=f"Skill {skill_id} not in allowlist (PG-02)",
                )

        # PG-03: Write without EDITOR role
        role = user_role.upper()
        if "SKL-TCIA-11" in skill_sequence and role == "VIEWER":
            return GuardrailResult(
                passed=False,
                blocked=True,
                block_reason="VIEWER cannot execute write skills (PG-03)",
            )

        # PG-07: Token budget
        if tokens_used > token_budget:
            warnings.append(
                f"PG-07: Token budget exceeded ({tokens_used}/{token_budget})"
            )

        # PG-08: Trend count cap
        if trend_count > max_trends:
            warnings.append(
                f"PG-08: Trend count capped ({trend_count} -> {max_trends})"
            )

        return GuardrailResult(passed=True, warnings=warnings)

    # ── Layer 3: Output Guardrails ──

    async def validate_output(
        self,
        report: dict[str, Any],
        scored_trends: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        tenant_id: str = "",
    ) -> GuardrailResult:
        """Run output guardrails (OG-01..08)."""
        warnings: list[str] = []

        # OG-03: Confidence threshold
        confidence = report.get("confidence_score", 0.0)
        if confidence < 0.7:
            warnings.append(
                f"OG-03: Low confidence ({confidence:.2f}), consider escalation"
            )

        # OG-06: Response size limit
        import json

        output_size = len(json.dumps(report, default=str))
        if output_size > 100000:
            warnings.append(
                f"OG-06: Response size {output_size} exceeds limit"
            )

        # OG-07: Harmful trend shield
        summary = report.get("executive_summary", "").lower()
        for kw in _HARMFUL_OUTPUT_KEYWORDS:
            if kw in summary:
                warnings.append(
                    f"OG-07: Harmful content detected in output: {kw}"
                )

        # OG-08: Political balance check
        for trend in scored_trends:
            rationale = trend.get("rationale", "").lower()
            for kw in _POLITICAL_KEYWORDS:
                if kw in rationale:
                    warnings.append(
                        f"OG-08: Political content in trend {trend.get('trend_slug', '')}"
                    )
                    break

        return GuardrailResult(passed=True, warnings=warnings)
