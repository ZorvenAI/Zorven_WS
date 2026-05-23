"""Build context dicts from onboarding data for template formatting (AC-1).

All values are stringified to prevent PII from leaking into prompt
templates. GEPA only sees the instruction layer — {context.*}
placeholders are filled at runtime.
"""

from typing import Any, Optional


def build_context_from_onboarding(
    onboarding_data: dict[str, Any],
    runtime_data: Optional[dict[str, Any]] = None,
    upstream_data: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    """Build a context dict with {context.*} keys.

    Args:
        onboarding_data: Tenant onboarding data (brand_name, industry, etc.)
        runtime_data: Per-request runtime data (query, budget, etc.)
        upstream_data: Outputs from upstream pipeline agents.

    Returns:
        Dict with context.* keys and stringified values.
    """
    context: dict[str, str] = {}

    # Onboarding fields → context.* keys
    _ONBOARDING_MAP = {
        "brand_name": "context.brand_name",
        "company_name": "context.brand_name",
        "industry": "context.industry",
        "industry_type": "context.industry",
        "target_audience": "context.target_audience",
        "brand_voice": "context.brand_voice",
        "product_description": "context.product_description",
        "founder_info": "context.founder_info",
    }

    for src_key, ctx_key in _ONBOARDING_MAP.items():
        value = onboarding_data.get(src_key)
        if value is not None:
            context[ctx_key] = str(value)

    # Runtime data (pass through with context. prefix, skip None)
    if runtime_data:
        for key, value in runtime_data.items():
            if value is None:
                continue
            ctx_key = key if key.startswith("context.") else f"context.{key}"
            context[ctx_key] = str(value)

    # Upstream data (pass through with context. prefix, skip None)
    if upstream_data:
        for key, value in upstream_data.items():
            if value is None:
                continue
            ctx_key = key if key.startswith("context.") else f"context.{key}"
            context[ctx_key] = str(value)

    return context
