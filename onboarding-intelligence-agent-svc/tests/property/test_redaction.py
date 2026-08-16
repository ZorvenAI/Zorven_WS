"""G-01 · Property tests for PII redaction: allowlist and idempotency.

The allowlist invariant: any term the operator added to the allowlist must
never appear as a detected entity type — the brand identity is not
collateral damage.

The idempotency invariant: redacting already-redacted text must produce
the same text — a double-redaction that corrupts ``<PERSON>`` into
``<PERSON><PERSON>`` breaks the replay buffer.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.skills.redact_pii import RedactionResult, redact_text

pytestmark = [pytest.mark.property, pytest.mark.unit]

BRAND_NAMES = st.sampled_from(
    [
        "Kelso Coffee",
        "Marlow & Sons",
        "Sadie's Vintage",
        "Phoenix Digital",
        "Jordan River Brewing",
        "Austin Holdings",
        "Brooklyn Supply",
    ]
)


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(brand=BRAND_NAMES)
def test_allowlisted_brand_never_redacted(brand):
    """AC-3: a term in the allowlist survives redaction."""
    text = f"We discussed {brand} and their new strategy."
    result = redact_text(text, allowlist=[brand])
    assert brand in result.text, f"{brand} was redacted despite being allowlisted"


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    text=st.sampled_from(
        [
            "Sarah called about the order.",
            "Call 555-867-5309 for details.",
            "Email john@example.com for updates.",
            "My SSN is 456-78-9012 on file.",
            "Sarah from Kelso Coffee mentioned the expansion.",
            "We started roasting in 2016.",
            "The quarterly review is complete.",
        ]
    )
)
def test_redaction_idempotent(text):
    """Redacting already-redacted text produces the same result."""
    first = redact_text(text)
    second = redact_text(first.text)

    assert (
        second.text == first.text
    ), f"double redaction changed text: {first.text!r} -> {second.text!r}"


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(brand=BRAND_NAMES)
def test_allowlist_case_insensitive_property(brand):
    """The allowlist match is case-insensitive in all directions."""
    text = f"Meeting notes from {brand} discussion."
    for variant in [brand.lower(), brand.upper(), brand.title()]:
        result = redact_text(text, allowlist=[variant])
        assert (
            brand in result.text
        ), f"{brand} was redacted with allowlist variant {variant!r}"


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(brand=BRAND_NAMES)
def test_result_is_always_a_redaction_result(brand):
    """The return type is always RedactionResult, never a raw string."""
    result = redact_text(f"Meeting with {brand}.")
    assert isinstance(result, RedactionResult)
    assert isinstance(result.text, str)
    assert isinstance(result.applied, bool)
    assert isinstance(result.entity_types, list)
