"""J-04 / M-01 — output guardrails OG-02 through OG-05.

Chain-compatible rule functions for the OUTPUT layer. Registered at
startup in ``app/main.py`` and also called inline during field
extraction (sole defense for PROCESS mode, which bypasses the chain).

Also exports ``UUID_RE``, ``scan_for_foreign_tenant``, and
``redact_value`` — shared helpers consumed by ``field_extractor.py``.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = get_logger(__name__)

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def scan_for_foreign_tenant(value: Any, own_tenant_id: str) -> str | None:
    """Recursively scan a value for UUID strings that aren't the own tenant."""
    if isinstance(value, str):
        for match in UUID_RE.finditer(value):
            found = match.group().lower()
            if found != own_tenant_id.lower():
                return found
    elif isinstance(value, dict):
        for v in value.values():
            result = scan_for_foreign_tenant(v, own_tenant_id)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = scan_for_foreign_tenant(item, own_tenant_id)
            if result is not None:
                return result
    return None


_URL_KEYS = frozenset(
    {
        "source_url",
        "url",
        "website",
        "href",
        "link",
        "social_profiles",
        "sources",
    }
)

#: A whole string that is just a URL or bare host, with no spaces.
#:
#: Deliberately strict. A bare email does not match — `[\w.-]+` cannot cross the
#: `@` — so `john@acme.com` under a `website` key is still redacted.
_URL_RE = re.compile(
    r"^(?:https?://|www\.)?[\w.-]+\.[a-z]{2,}(?:[/?#]\S*)?$",
    re.IGNORECASE,
)


def _is_url(value: str) -> bool:
    candidate = value.strip()
    if not candidate or " " in candidate:
        return False
    return bool(_URL_RE.match(candidate))


def redact_value(
    value: Any, *, allowlist: list[str] | None = None, _key: str = ""
) -> tuple[Any, bool]:
    """Recursively redact PII in strings, dicts, and lists.

    A string under a URL-ish key is left alone **only when it is actually a
    URL**, because redacting inside one destroys it rather than protecting
    anyone — and grounding depends on a citation URL matching the retrieved set
    exactly.

    The check is per string, after the type dispatch, not per key before it.
    Keyed on the container, `social_profiles: ["twitter.com/acme", "CEO John Doe
    - john@acme.com"]` returned unchanged in full: the key matched, so the list
    was never walked and the email and name went out intact (#654).

    Residual risk, accepted: PII inside a URL's own query string survives, since
    narrowing further would start mangling the citations the exemption exists to
    protect.
    """
    from app.skills.redact_pii import redact_text

    if isinstance(value, str):
        if _key in _URL_KEYS and _is_url(value):
            return value, False
        result = redact_text(value, allowlist=allowlist)
        return result.text, result.applied
    elif isinstance(value, dict):
        changed = False
        out: dict[str, Any] = {}
        for k, v in value.items():
            new_v, did_change = redact_value(v, allowlist=allowlist, _key=k)
            out[k] = new_v
            changed = changed or did_change
        return out, changed
    elif isinstance(value, list):
        changed = False
        out_list: list[Any] = []
        for item in value:
            new_item, did_change = redact_value(item, allowlist=allowlist, _key=_key)
            out_list.append(new_item)
            changed = changed or did_change
        return out_list, changed
    return value, False


def _extract_business_names(payload: Any) -> list[str]:
    """Pull company/brand names from the research brief for the allowlist."""
    names: list[str] = []
    if not isinstance(payload, dict):
        return names
    cn = payload.get("company_name")
    if cn and isinstance(cn, str):
        names.append(cn)
    for comp in payload.get("competitors_seen") or []:
        if isinstance(comp, str) and comp.strip():
            names.append(comp.strip())
    for fact in payload.get("facts") or []:
        if isinstance(fact, dict):
            stmt = fact.get("statement", "")
            for token in _KNOWN_TECH_BRANDS:
                if token.lower() in stmt.lower():
                    names.append(token)
    return names


_KNOWN_TECH_BRANDS = [
    "Shopify",
    "Zapier",
    "Looker",
    "HubSpot",
    "Mailchimp",
    "Canva",
    "Salesforce",
    "Stripe",
    "Figma",
    "Notion",
    "Slack",
    "Asana",
    "Monday",
    "Trello",
    "Airtable",
    "Webflow",
    "Squarespace",
    "Wix",
    "WordPress",
    "Semrush",
    "Ahrefs",
    "Moz",
    "Hootsuite",
    "Buffer",
    "Sprout",
    "Marketo",
    "Pardot",
    "ActiveCampaign",
    "Klaviyo",
    "Google",
    "Meta",
    "Facebook",
    "Instagram",
    "TikTok",
    "LinkedIn",
    "Twitter",
    "YouTube",
    "Pinterest",
    "Amazon",
    "Microsoft",
    "Adobe",
    "Oracle",
    "SAP",
    "Zendesk",
    "Intercom",
    "Drift",
    "Freshworks",
]


def og02_egress_redact(payload: Any, context: SkillContext) -> Verdict:
    """OG-02: re-apply PII redaction on output before delivery."""
    allowlist: list[str] = []
    company_name = (context.input_context or {}).get("company_name", "")
    if company_name:
        allowlist.append(company_name)
    allowlist.extend(_extract_business_names(payload))
    new_payload, changed = redact_value(payload, allowlist=allowlist)
    if changed:
        logger.info(
            "og02_chain_redaction",
            detail="PII redacted from output",
        )
        return Verdict(
            rule_id="OG-02",
            action=Action.REDACT,
            detail="PII redacted from output",
            payload=new_payload,
        )
    return Verdict(rule_id="OG-02", action=Action.PASS, payload=payload)


def og05_tenant_isolation(payload: Any, context: SkillContext) -> Verdict:
    """OG-05: cross-tenant identifier in output → security BLOCK."""
    own_tenant = context.tenant_context.tenant_id
    if not own_tenant:
        return Verdict(rule_id="OG-05", action=Action.PASS, payload=payload)

    foreign = scan_for_foreign_tenant(payload, own_tenant)
    if foreign is not None:
        logger.error(
            "og05_chain_cross_tenant_block",
            foreign_tenant_id=foreign,
            detail="cross-tenant identifier in output",
        )
        return Verdict(
            rule_id="OG-05",
            action=Action.BLOCK,
            detail=f"cross-tenant identifier {foreign} found in output",
        )

    return Verdict(rule_id="OG-05", action=Action.PASS, payload=payload)


def og03_confidence_gate(payload: Any, context: SkillContext) -> Verdict:
    """OG-03: fields below the confidence threshold default to KEY."""
    if not isinstance(payload, dict):
        return Verdict(rule_id="OG-03", action=Action.PASS, payload=payload)

    threshold = context.config.get("_og03_threshold", 0.6)
    confidence = payload.get("confidence")
    if confidence is not None and isinstance(confidence, (int, float)):
        if confidence < threshold:
            payload = dict(payload)
            payload["classification"] = "KEY"
            logger.info(
                "og03_forced_key",
                confidence=confidence,
                threshold=threshold,
            )
            return Verdict(
                rule_id="OG-03",
                action=Action.REDACT,
                detail=f"confidence {confidence} < {threshold}, forced to KEY",
                payload=payload,
            )
    return Verdict(rule_id="OG-03", action=Action.PASS, payload=payload)


def og04_sampled_judge(payload: Any, context: SkillContext) -> Verdict:
    """OG-04: stash payload for async LLM judge if this request was sampled.

    The chain rule always returns PASS — the LLM call is fire-and-forget,
    spawned by the async caller after the chain completes.
    """
    sampled = context.config.get("_og04_sample_selected", False)
    if sampled:
        context.config["_og04_payload"] = payload
    return Verdict(rule_id="OG-04", action=Action.PASS, payload=payload)
