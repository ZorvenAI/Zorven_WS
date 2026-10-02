"""OG-02 · the URL exemption must not become a PII hole (#654, #655).

`redact_value` leaves URLs alone because redacting inside one destroys it, and
grounding depends on a citation URL matching the retrieved set byte for byte.
The exemption was keyed on the *container* and checked before the type
dispatch, so any list or dict under a URL-ish key was returned whole and
unwalked — which is a PII hole wearing the costume of a URL fix.
"""

from __future__ import annotations

import importlib.util

import pytest

from app.logic.output_guardrails import _is_url, redact_value

pytestmark = pytest.mark.unit

#: PERSON detection comes from presidio's NER. Without it `redact_text` falls
#: back to patterns, which cover emails and phone numbers but not names — so the
#: analyser produces no results for a person-shaped string and the allowlist has
#: nothing to filter. These tests would then pass whether or not the allowlist
#: was threaded through at all, which is worse than not having them.
requires_ner = pytest.mark.skipif(
    importlib.util.find_spec("presidio_analyzer") is None,
    reason="needs presidio NER; the allowlist is unobservable without PERSON detection",
)


# ── #654 · the container is walked, the URL is spared ────────────────


def test_a_list_under_a_url_key_is_still_walked():
    """The reported leak, verbatim.

    The key matched, so the whole list was returned untouched and the email and
    the person's name went out intact.
    """
    value = {
        "social_profiles": ["twitter.com/acme", "CEO John Doe - john@acme.com"],
    }

    redacted, changed = redact_value(value)

    assert changed is True
    profiles = redacted["social_profiles"]
    # The real URL survives — that is what the exemption is for.
    assert profiles[0] == "twitter.com/acme"
    # The prose does not.
    assert "john@acme.com" not in profiles[1]


def test_a_dict_under_a_url_key_is_still_walked():
    value = {"sources": {"contact": "reach me at john@acme.com"}}

    redacted, changed = redact_value(value)

    assert changed is True
    assert "john@acme.com" not in redacted["sources"]["contact"]


def test_a_citation_url_is_left_exactly_as_it_was():
    """Grounding compares a fact's source_url against the retrieved set, so a
    single altered character turns a sourced fact into an unsourced one."""
    url = "https://example.com/a-b_c?q=1&r=2#frag"

    redacted, changed = redact_value({"source_url": url})

    assert redacted["source_url"] == url
    assert changed is False


def test_an_email_under_a_url_key_is_not_mistaken_for_a_url():
    """A `website` field holding a contact address is the case the key-based
    exemption got wrong, and the narrow one it has to keep getting right."""
    redacted, changed = redact_value({"website": "john@acme.com"})

    assert changed is True
    assert "john@acme.com" not in redacted["website"]


def test_prose_mentioning_a_domain_is_redacted():
    redacted, changed = redact_value(
        {"website": "their site is acme.com, ask for john@acme.com"}
    )

    assert changed is True
    assert "john@acme.com" not in redacted["website"]


def test_a_non_url_key_never_gets_the_exemption():
    """Only the named keys are exempt. A URL under `notes` is prose as far as
    this rule is concerned, and must not acquire an exemption by looking like
    a URL."""
    redacted, _ = redact_value({"notes": "john@acme.com"})

    assert "john@acme.com" not in redacted["notes"]


# ── #655 · the allowlist reaches every path ──────────────────────────


@requires_ner
def test_an_allowlisted_company_name_survives():
    """A person-shaped business name is the company's identity, not a leak.

    Without this the brand profile built from a company's own meeting called it
    "<PERSON> Consulting".
    """
    redacted, _ = redact_value(
        {"name": "Sarah Johnson Consulting"},
        allowlist=["Sarah Johnson Consulting"],
    )

    assert redacted["name"] == "Sarah Johnson Consulting"


@requires_ner
def test_the_allowlist_reaches_values_nested_in_lists_and_dicts():
    """It is threaded through both recursive branches, or a name survives at the
    top level and is redacted one layer down."""
    redacted, _ = redact_value(
        {"pages": [{"name": "Sarah Johnson Consulting"}]},
        allowlist=["Sarah Johnson Consulting"],
    )

    assert redacted["pages"][0]["name"] == "Sarah Johnson Consulting"


# ── _is_url ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://example.com/path",
        "www.example.com",
        "example.com",
        "twitter.com/acme",
        "example.co.uk/a?b=c",
    ],
)
def test_urls_are_recognised(value):
    assert _is_url(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "john@acme.com",
        "CEO John Doe - john@acme.com",
        "their site is acme.com",
        "Sarah Johnson",
        "no dot here",
    ],
)
def test_non_urls_are_rejected(value):
    assert _is_url(value) is False
