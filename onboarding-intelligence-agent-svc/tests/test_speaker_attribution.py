"""O-08 · speaker attribution in evidence text.

Unit tests for the pure half of AC-3. The assembler-level behaviour lives in
`test_evidence_assembly.py`, which needs real Redis; this does not, and the
rules it pins down — what gets a label, what deliberately does not — are the
ones a future change is most likely to get wrong.
"""

from __future__ import annotations

import pytest

from app.logic.evidence_assembler import attribute_segment

pytestmark = pytest.mark.unit


def test_a_named_speaker_is_prefixed():
    assert (
        attribute_segment("we roast in Kalyani", "Sarah Kelso")
        == "Sarah Kelso: we roast in Kalyani"
    )


@pytest.mark.parametrize("missing", [None, "", "   ", "\t"])
def test_an_unnamed_speaker_gets_no_label(missing):
    """AC-2. A single-mic recording has no mic-to-attendee map.

    Whitespace counts as unnamed: a label of ": text" is worse than no label,
    because it reads as an attribution to nobody.
    """
    assert attribute_segment("we started in 2019", missing) == "we started in 2019"


def test_the_text_is_never_altered():
    """Attribution prefixes; it must not rewrite. Evidence spans point back at
    this text, and a transcript that reworded what someone said would not be
    the legal record O-06 assembles."""
    said = "no, we are direct to consumer — always have been"

    result = attribute_segment(said, "Sarah Kelso")

    assert result.endswith(said)
    assert result.count(said) == 1


def test_a_name_with_surrounding_whitespace_is_tidied():
    """Roll call is voice-driven (O-05), so a captured name can arrive padded."""
    assert attribute_segment("hello", "  Devan Roy  ") == "Devan Roy: hello"


def test_a_colon_in_the_spoken_text_is_left_alone():
    """Only the prefix is added; punctuation inside the utterance is the
    speaker's, not ours to normalise."""
    result = attribute_segment("the ratio is 2:1", "Sarah Kelso")

    assert result == "Sarah Kelso: the ratio is 2:1"
