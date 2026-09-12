"""IG-01 through IG-09 (excluding IG-04, IG-08, IG-10) — input guardrails.

Design §5.1 · implemented by story M-01.

IG-04 (PII redaction) lives in ``app/skills/redact_pii.py``.
IG-08 (consent gate) lives in ``app/logic/consent_gate.py``.
IG-10 (live gate) lives in ``app/logic/live_gate.py``.

Rules in this module are pure — no I/O. Where async state is needed
(IG-07 rate count, IG-09 company existence), the caller pre-fetches it
and stores the result on ``context.config`` before entering the chain.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = get_logger(__name__)


def ig01_prompt_injection(payload: Any, context: SkillContext) -> Verdict:
    """IG-01: block prompt-injection patterns."""
    patterns = context.config.get("_injection_patterns", [])
    text = _payload_text(payload)
    if not text or not patterns:
        return Verdict(rule_id="IG-01", action=Action.PASS, payload=payload)

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            logger.warning("ig01_injection_detected", pattern=pattern)
            return Verdict(
                rule_id="IG-01",
                action=Action.BLOCK,
                detail=f"prompt injection pattern detected: {pattern}",
            )
    return Verdict(rule_id="IG-01", action=Action.PASS, payload=payload)


def ig02_scam_filter(payload: Any, context: SkillContext) -> Verdict:
    """IG-02: block scam/fraud patterns."""
    patterns = context.config.get("_scam_patterns", [])
    text = _payload_text(payload)
    if not text or not patterns:
        return Verdict(rule_id="IG-02", action=Action.PASS, payload=payload)

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            logger.warning("ig02_scam_detected", pattern=pattern)
            return Verdict(
                rule_id="IG-02",
                action=Action.BLOCK,
                detail=f"scam pattern detected: {pattern}",
            )
    return Verdict(rule_id="IG-02", action=Action.PASS, payload=payload)


def ig03_scope_filter(payload: Any, context: SkillContext) -> Verdict:
    """IG-03: scope relevance via Jaccard similarity."""
    scope_terms = context.config.get("_scope_terms", [])
    threshold = context.config.get("_scope_threshold", 0.55)
    text = _payload_text(payload)
    if not text or not scope_terms:
        return Verdict(rule_id="IG-03", action=Action.PASS, payload=payload)

    score = _jaccard_score(text, scope_terms)
    if score < threshold:
        logger.info("ig03_out_of_scope", score=round(score, 3), threshold=threshold)
        return Verdict(
            rule_id="IG-03",
            action=Action.ESCALATE,
            detail=f"input relevance {score:.2f} below threshold {threshold}",
            payload=payload,
        )
    return Verdict(rule_id="IG-03", action=Action.PASS, payload=payload)


def ig05_tenant_context(payload: Any, context: SkillContext) -> Verdict:
    """IG-05: tenant id on the request must match the authenticated tenant."""
    if not isinstance(payload, dict):
        return Verdict(rule_id="IG-05", action=Action.PASS, payload=payload)

    request_tenant = payload.get("x_tenant_id") or payload.get("tenant_id")
    own_tenant = context.tenant_context.tenant_id
    if not request_tenant or not own_tenant:
        return Verdict(rule_id="IG-05", action=Action.PASS, payload=payload)

    if str(request_tenant).lower() != str(own_tenant).lower():
        logger.error("ig05_tenant_mismatch", request=request_tenant, own=own_tenant)
        return Verdict(
            rule_id="IG-05",
            action=Action.BLOCK,
            detail="tenant id mismatch between request and authenticated context",
        )
    return Verdict(rule_id="IG-05", action=Action.PASS, payload=payload)


def ig06_input_size(payload: Any, context: SkillContext) -> Verdict:
    """IG-06: truncate input exceeding the token budget."""
    max_tokens = context.config.get("_input_max_tokens", 4096)
    text = _payload_text(payload)
    if not text:
        return Verdict(rule_id="IG-06", action=Action.PASS, payload=payload)

    tokens = text.split()
    if len(tokens) > max_tokens:
        truncated = " ".join(tokens[:max_tokens])
        if isinstance(payload, dict):
            payload = dict(payload)
            for key in ("input_prompt", "text", "content", "prompt"):
                if key in payload and isinstance(payload[key], str):
                    payload[key] = truncated
                    break
        logger.info(
            "ig06_truncated",
            original_tokens=len(tokens),
            max_tokens=max_tokens,
        )
        return Verdict(
            rule_id="IG-06",
            action=Action.TRUNCATE,
            detail=f"input truncated from {len(tokens)} to {max_tokens} tokens",
            payload=payload,
        )
    return Verdict(rule_id="IG-06", action=Action.PASS, payload=payload)


def ig07_rate_limit(payload: Any, context: SkillContext) -> Verdict:
    """IG-07: block when the pre-fetched rate counter exceeds the limit."""
    count = context.config.get("_ig07_count", 0)
    limit = context.config.get("_rate_limit", 10)
    if count >= limit:
        logger.warning("ig07_rate_exceeded", count=count, limit=limit)
        return Verdict(
            rule_id="IG-07",
            action=Action.BLOCK,
            detail=f"rate limit exceeded: {count}/{limit} per minute",
        )
    return Verdict(rule_id="IG-07", action=Action.PASS, payload=payload)


def ig09_brand_identity(payload: Any, context: SkillContext) -> Verdict:
    """IG-09: escalate when no company exists and auto-create is off."""
    company_exists = context.config.get("_ig09_company_exists")
    auto_create = context.config.get("_auto_create_company", True)
    if company_exists is None or company_exists:
        return Verdict(rule_id="IG-09", action=Action.PASS, payload=payload)

    if not auto_create:
        logger.info("ig09_no_company")
        return Verdict(
            rule_id="IG-09",
            action=Action.ESCALATE,
            detail="no company found and auto-creation is disabled",
            payload=payload,
        )
    return Verdict(rule_id="IG-09", action=Action.PASS, payload=payload)


def _payload_text(payload: Any) -> str:
    """Extract text content from various payload shapes."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("input_prompt", "text", "content", "prompt"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


def _jaccard_score(text: str, terms: list[str]) -> float:
    """Jaccard similarity between lowered word tokens and a term set."""
    words = set(text.lower().split())
    term_set = {t.lower() for t in terms}
    if not words or not term_set:
        return 0.0
    intersection = words & term_set
    union = words | term_set
    return len(intersection) / len(union)
