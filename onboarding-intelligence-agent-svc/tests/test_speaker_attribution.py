"""O-08 · speaker attribution in prompts.

Attribution is by **role**, not name. SKL-OIA-16 redacts PERSON out of the
transcript body before it is stored, so prefixing each line with the attendee's
real name would put back — on every line — exactly what the redaction pass
removed, in the payload sent to a model provider. "Operator" and "Participant"
carry the whole discriminative value extraction needs and identify nobody.

The persisted `speaker_name` is unaffected: that is the legal record, and it
stays in our own database.
"""

from __future__ import annotations

import pytest

from app.logic.evidence_assembler import (
    attribute_segment,
    build_speaker_labels,
    label_for,
)

pytestmark = pytest.mark.unit


# ── build_speaker_labels ─────────────────────────────────────────────


def test_a_two_mic_meeting_reads_operator_and_participant():
    segments = [
        {"speaker": 0, "speaker_role": "operator"},
        {"speaker": 1, "speaker_role": "participant"},
    ]

    assert build_speaker_labels(segments) == {0: "Operator", 1: "Participant"}


def test_speakers_sharing_a_role_are_numbered():
    """Two participants both labelled "Participant" would be indistinguishable,
    which defeats the point of attributing at all."""
    segments = [
        {"speaker": 0, "speaker_role": "operator"},
        {"speaker": 1, "speaker_role": "participant"},
        {"speaker": 2, "speaker_role": "participant"},
    ]

    assert build_speaker_labels(segments) == {
        0: "Operator",
        1: "Participant 1",
        2: "Participant 2",
    }


def test_no_name_ever_becomes_a_label():
    """The guardrail this design exists for: a real name on the segment must not
    reach the prompt."""
    segments = [
        {"speaker": 0, "speaker_role": "operator", "speaker_name": "Devan Roy"},
        {"speaker": 1, "speaker_role": "participant", "speaker_name": "Sarah Kelso"},
    ]

    labels = build_speaker_labels(segments)

    assert "Devan Roy" not in labels.values()
    assert "Sarah Kelso" not in labels.values()


def test_a_single_mic_transcript_yields_no_labels():
    """AC-2. No role map, so no labels — rather than "Speaker 0" on every line,
    which spends tokens to convey nothing."""
    segments = [
        {"speaker": 0, "text": "we started in 2019"},
        {"speaker": 0, "speaker_role": None},
    ]

    assert build_speaker_labels(segments) == {}


@pytest.mark.parametrize("junk", [3, 3.5, ["operator"], {"role": "operator"}, True])
def test_a_non_string_role_is_ignored_not_raised(junk):
    """The Django callback validates only text and timestamps, so any JSON type
    can reach this field. Evidence assembly calls this unguarded, so a raise
    would cost the whole session its evidence."""
    labels = build_speaker_labels([{"speaker": 0, "speaker_role": junk}])

    assert all(isinstance(v, str) for v in labels.values())


def test_a_non_integer_speaker_index_is_skipped():
    labels = build_speaker_labels(
        [
            {"speaker": "one", "speaker_role": "operator"},
            {"speaker": True, "speaker_role": "operator"},
            {"speaker": 1, "speaker_role": "participant"},
        ]
    )

    assert labels == {1: "Participant"}


def test_an_underscored_role_is_made_readable():
    labels = build_speaker_labels([{"speaker": 0, "speaker_role": "note_taker"}])

    assert labels == {0: "Note Taker"}


# ── attribute_segment ────────────────────────────────────────────────


def test_a_labelled_line_is_prefixed():
    assert (
        attribute_segment("we roast in Kalyani", "Participant")
        == "Participant: we roast in Kalyani"
    )


@pytest.mark.parametrize("missing", [None, "", "   ", "\t"])
def test_an_unlabelled_line_is_left_alone(missing):
    assert attribute_segment("we started in 2019", missing) == "we started in 2019"


def test_the_text_is_never_altered():
    """Attribution prefixes; it must not rewrite. Evidence spans point back at
    this text, and a transcript that reworded what someone said would not be the
    legal record O-06 assembles."""
    said = "no, we are direct to consumer — always have been"

    result = attribute_segment(said, "Participant")

    assert result.endswith(said)
    assert result.count(said) == 1


def test_a_colon_in_the_spoken_text_is_left_alone():
    assert (
        attribute_segment("the ratio is 2:1", "Participant")
        == "Participant: the ratio is 2:1"
    )


# ── label_for ────────────────────────────────────────────────────────


def test_a_real_index_resolves_to_its_label():
    assert label_for({0: "Operator", 1: "Participant"}, 1) == "Participant"


def test_a_boolean_does_not_alias_a_real_mic():
    """The reason this helper exists rather than a bare `labels.get(...)`.

    `hash(True) == hash(1)` and `True == 1`, so in a dict keyed by mic index
    `labels.get(True)` returns **mic 1's label** — verified. A malformed segment
    would therefore be attributed to a real speaker, and the attribution would
    look entirely plausible in the transcript.

    `build_speaker_labels` already refuses to build a label *from* a boolean;
    this is the other half, where a label for key 1 legitimately exists.
    """
    labels = {0: "Operator", 1: "Participant"}

    assert labels.get(True) == "Participant"  # what the guard is protecting against
    assert label_for(labels, True) is None
    assert label_for(labels, False) is None


@pytest.mark.parametrize(
    "speaker",
    [
        None,
        "1",
        1.0,
        [1],
        {"speaker": 1},
        (1,),
    ],
)
def test_a_malformed_index_resolves_to_nothing(speaker):
    """Segments come from a JSON column whose writer validates only text and
    timestamps, so any type can arrive here.

    The unhashable cases are the ones that matter most: `labels.get([1])` raises
    `TypeError: unhashable type`, and this runs inside evidence assembly, so it
    would cost a whole session its evidence rather than one segment its label.
    """
    assert label_for({0: "Operator", 1: "Participant"}, speaker) is None


def test_an_index_with_no_label_resolves_to_nothing():
    """A mic the START frame never described. Distinct from a malformed index,
    and handled the same way — no label rather than a guess."""
    assert label_for({0: "Operator"}, 7) is None


def test_an_empty_label_map_resolves_to_nothing():
    """A single-mic recording builds no labels at all."""
    assert label_for({}, 0) is None
