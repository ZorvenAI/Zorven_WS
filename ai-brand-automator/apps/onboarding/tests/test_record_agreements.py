"""Signed meeting records · step 2 — numbering agreements and fingerprinting.

Two things here must be true for a record to be worth signing:

- the numbered agreements are the stored text, word for word — the description
  is a legal record and is never reworded;
- the fingerprint is the same for the same content and different for any
  other content.

Neither needs a database.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.onboarding.records.agreements import split_agreements
from apps.onboarding.records.snapshot import (
    all_text,
    canonical_json,
    content_hash,
    transcript_lines,
)

DESCRIPTION = (
    "## Agreements\n"
    "- **Budget split:** launch budget split evenly; proposed by the operator, "
    "accepted by the participant (~12:30).\n"
    "- Contract review before launch; proposed by the participant, accepted by "
    "the operator (~21:05).\n"
    "\n"
    "## Business Identity\n"
    "Pomodoro is a family restaurant.\n"
    "- Dine-in and takeout\n"
)


# ── Finding and numbering ────────────────────────────────────────────


@pytest.mark.unit
def test_each_bullet_becomes_a_numbered_agreement_in_order():
    split = split_agreements(DESCRIPTION)

    assert [a.number for a in split.agreements] == ["A-1", "A-2"]
    assert split.agreements[0].text == (
        "**Budget split:** launch budget split evenly; proposed by the operator, "
        "accepted by the participant (~12:30)."
    )
    assert split.agreements[1].text.startswith("Contract review before launch;")


@pytest.mark.unit
def test_the_agreement_text_is_the_stored_text_word_for_word():
    """Never reworded: every agreement appears verbatim in the description."""
    split = split_agreements(DESCRIPTION)

    for agreement in split.agreements:
        assert agreement.text in DESCRIPTION


@pytest.mark.unit
def test_the_rest_of_the_description_is_left_exactly_as_it_was():
    split = split_agreements(DESCRIPTION)

    assert split.remainder == (
        "## Business Identity\n"
        "Pomodoro is a family restaurant.\n"
        "- Dine-in and takeout\n"
    )
    assert "Budget split" not in split.remainder


@pytest.mark.unit
def test_bullets_in_other_sections_are_not_agreements():
    split = split_agreements(DESCRIPTION)

    assert all("Dine-in" not in a.text for a in split.agreements)
    assert len(split.agreements) == 2


@pytest.mark.unit
def test_a_description_with_no_agreements_section_has_none():
    """The description said none were made; that is recorded, not guessed at."""
    text = "## Business Identity\nPomodoro.\n- Dine-in\n"

    split = split_agreements(text)

    assert split.agreements == ()
    assert split.remainder == text
    assert split.section == ""


@pytest.mark.unit
def test_an_agreements_section_at_the_end_runs_to_the_end():
    text = "## Business Identity\nPomodoro.\n\n## Agreements\n- Launch in March.\n"

    split = split_agreements(text)

    assert [a.text for a in split.agreements] == ["Launch in March."]
    assert split.remainder == "## Business Identity\nPomodoro.\n\n"


@pytest.mark.unit
def test_a_continuation_line_belongs_to_the_agreement_above_it():
    text = (
        "## Agreements\n"
        "- Launch in March;\n"
        "  subject to the kitchen refit finishing.\n"
        "- Weekly check-ins.\n"
    )

    split = split_agreements(text)

    assert [a.text for a in split.agreements] == [
        "Launch in March;\nsubject to the kitchen refit finishing.",
        "Weekly check-ins.",
    ]


@pytest.mark.unit
def test_a_nested_bullet_is_part_of_its_agreement_not_a_new_one():
    text = "## Agreements\n- Budget agreed:\n    - 60% social\n    - 40% search\n"

    split = split_agreements(text)

    assert len(split.agreements) == 1
    assert "60% social" in split.agreements[0].text
    assert "40% search" in split.agreements[0].text


@pytest.mark.unit
@pytest.mark.parametrize("rule", ["---", "***", "___", "- - -", "* * *", "-----"])
def test_a_divider_after_the_section_is_not_part_of_the_last_agreement(rule):
    """Found on real data: the description ends its Agreements section with a
    rule, and the last agreement was printed with ``---`` on the end."""
    text = (
        f"## Agreements\n- Launch in March.\n\n{rule}\n\n"
        "## Business Identity\nPomodoro.\n"
    )

    split = split_agreements(text)

    assert [a.text for a in split.agreements] == ["Launch in March."]
    assert split.original == text


@pytest.mark.unit
def test_text_before_the_first_bullet_is_kept_as_a_preamble():
    text = "## Agreements\nBoth parties confirmed the following.\n- Launch in March.\n"

    split = split_agreements(text)

    assert split.preamble == "Both parties confirmed the following."
    assert [a.text for a in split.agreements] == ["Launch in March."]


@pytest.mark.unit
@pytest.mark.parametrize(
    "heading", ["## Agreements", "## agreements", "##  Agreements:", "## AGREEMENTS  "]
)
def test_the_heading_is_matched_however_it_was_typed(heading):
    split = split_agreements(f"{heading}\n- Launch in March.\n")

    assert [a.text for a in split.agreements] == ["Launch in March."]


@pytest.mark.unit
def test_a_heading_that_only_mentions_agreements_is_not_the_section():
    text = "## Disagreements and Agreements Pending\n- Not settled.\n"

    assert split_agreements(text).agreements == ()


@pytest.mark.unit
def test_an_empty_description_has_no_agreements():
    split = split_agreements("")

    assert split.agreements == ()
    assert split.remainder == ""


_LINES = st.lists(
    st.one_of(
        st.just("## Agreements"),
        st.just("## Business Identity"),
        st.just(""),
        st.text(alphabet="abc -*#:\t", max_size=12),
        st.text(max_size=30).filter(lambda t: "\n" not in t and "\r" not in t),
    ),
    max_size=14,
)


@pytest.mark.property
@given(_LINES, st.sampled_from(["\n", "\r\n"]), st.booleans())
def test_the_split_is_lossless_for_any_description(lines, newline, trailing):
    """Whatever the text, nothing is dropped, added or reordered: the three
    parts put back together are the original, character for character."""
    text = newline.join(lines) + (newline if trailing else "")

    split = split_agreements(text)

    assert split.before + split.section + split.after == text
    assert split.original == text


@pytest.mark.property
@given(_LINES)
def test_every_agreement_line_comes_from_the_original_text(lines):
    text = "\n".join(lines)

    for agreement in split_agreements(text).agreements:
        for part in agreement.text.split("\n"):
            assert part in text


@pytest.mark.property
@given(_LINES)
def test_agreements_are_numbered_contiguously_from_one(lines):
    agreements = split_agreements("\n".join(lines)).agreements

    assert [a.number for a in agreements] == [
        f"A-{i}" for i in range(1, len(agreements) + 1)
    ]


# ── Transcript lines ─────────────────────────────────────────────────


@pytest.mark.unit
def test_a_string_transcript_becomes_its_non_blank_lines():
    assert transcript_lines("Naveen: Hello\n\nMaria: Hi there  \n") == [
        "Naveen: Hello",
        "Maria: Hi there",
    ]


@pytest.mark.unit
def test_a_segment_transcript_becomes_speaker_lines():
    segments = [
        {"speaker": "Naveen", "text": "Hello"},
        {"speaker": 1, "text": "Hi there"},
        {"speaker": "Naveen", "text": "   "},
        {"text": "No speaker given"},
    ]

    assert transcript_lines(segments) == [
        "Naveen: Hello",
        "Speaker 1: Hi there",
        "No speaker given",
    ]


@pytest.mark.unit
@pytest.mark.parametrize("empty", ["", [], None])
def test_no_transcript_is_no_lines(empty):
    assert transcript_lines(empty) == []


# ── The fingerprint ──────────────────────────────────────────────────

SNAPSHOT = {
    "schema": 1,
    "record": {"number": "MR-000085-v1", "version": 1, "supersedes": None},
    "parties": {"agency": {"name": "Zorven"}, "client": {"name": "Pomodoro"}},
    "agreements": {"preamble": "", "items": [{"number": "A-1", "text": "Launch."}]},
    "description": "## Business Identity\nPomodoro.",
    "transcript": ["Naveen: Hello", "Maria: Hi — ₹50,000"],
}


def _reordered(value):
    """The same content with every dict's keys in reverse insertion order."""
    if isinstance(value, dict):
        return {key: _reordered(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


@pytest.mark.unit
def test_the_fingerprint_is_a_sha256_of_the_canonical_form():
    import hashlib

    assert (
        content_hash(SNAPSHOT) == hashlib.sha256(canonical_json(SNAPSHOT)).hexdigest()
    )
    assert len(content_hash(SNAPSHOT)) == 64


@pytest.mark.unit
def test_key_order_does_not_change_the_fingerprint():
    assert content_hash(_reordered(SNAPSHOT)) == content_hash(SNAPSHOT)


@pytest.mark.unit
def test_non_ascii_text_is_fingerprinted_as_written():
    """Escaping would make ``₹`` and its escape sequence indistinguishable
    from a snapshot that literally contained the escape."""
    assert "₹50,000".encode() in canonical_json(SNAPSHOT)


@pytest.mark.unit
def test_changing_one_transcript_character_changes_the_fingerprint():
    changed = copy.deepcopy(SNAPSHOT)
    changed["transcript"][1] = "Maria: Hi — ₹15,000"

    assert content_hash(changed) != content_hash(SNAPSHOT)


@pytest.mark.unit
def test_reordering_transcript_lines_changes_the_fingerprint():
    """List order is content: who spoke first is part of what was said."""
    changed = copy.deepcopy(SNAPSHOT)
    changed["transcript"].reverse()

    assert content_hash(changed) != content_hash(SNAPSHOT)


_JSON = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=12)),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=6), children, max_size=4),
    ),
    max_leaves=12,
)


@pytest.mark.property
@given(st.dictionaries(st.text(max_size=6), _JSON, max_size=5))
def test_any_content_fingerprints_the_same_regardless_of_key_order(snapshot):
    assert content_hash(_reordered(snapshot)) == content_hash(snapshot)


@pytest.mark.property
@given(
    st.lists(st.text(max_size=20), min_size=1, max_size=6),
    st.data(),
)
def test_changing_any_one_line_changes_the_fingerprint(lines, data):
    index = data.draw(st.integers(min_value=0, max_value=len(lines) - 1))
    replacement = data.draw(st.text(max_size=20).filter(lambda t: t != lines[index]))
    original = {"transcript": lines}
    changed = {"transcript": [*lines[:index], replacement, *lines[index + 1 :]]}

    assert content_hash(changed) != content_hash(original)


@pytest.mark.unit
def test_all_text_gathers_every_string_a_record_prints():
    text = all_text(SNAPSHOT)

    assert "MR-000085-v1" in text
    assert "Maria: Hi — ₹50,000" in text
    assert "Launch." in text
