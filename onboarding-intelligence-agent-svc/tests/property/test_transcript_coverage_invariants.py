"""Property tests for #662 transcript coverage.

The example-based tests in ``tests/test_summarize_recording.py`` cover the
marker sequences we thought of: one drop, two drops, a repeat, a stray resume.
These check the ones we did not — markers in any order, markers outside the
recording window, resumes without interruptions, and degenerate windows where
the recording has no duration at all.

The invariant that matters is the last one. Coverage must be driven by markers
and nothing else, because the alternative — inferring truncation from where the
transcript happens to stop — reports every recording that ended with a pause as
partial.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.skills.summarize_recording import compute_transcript_coverage

pytestmark = pytest.mark.property

#: Deliberately unbounded relative to the window, so markers land before
#: `started_at` and after `stopped_at` as well as inside.
marker_times = st.floats(min_value=-500.0, max_value=1500.0, allow_nan=False)

markers = st.lists(
    st.fixed_dictionaries(
        {
            "type": st.sampled_from(["transcript.interrupted", "transcript.resumed"]),
            "at": marker_times,
        }
    ),
    max_size=12,
)

windows = st.tuples(
    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
).map(lambda pair: (min(pair), max(pair)))


@settings(max_examples=300)
@given(markers=markers, window=windows)
def test_missing_never_exceeds_the_recording(markers, window):
    started_at, stopped_at = window
    coverage = compute_transcript_coverage(markers, started_at, stopped_at)

    assert coverage["missing_s"] >= 0.0
    assert coverage["missing_s"] <= coverage["recording_s"] + 1e-6


@settings(max_examples=300)
@given(markers=markers, window=windows)
def test_gaps_lie_inside_the_window_and_run_forwards(markers, window):
    started_at, stopped_at = window
    coverage = compute_transcript_coverage(markers, started_at, stopped_at)

    for gap in coverage["gaps"]:
        assert started_at <= gap["from"] <= stopped_at
        assert started_at <= gap["to"] <= stopped_at
        assert gap["to"] > gap["from"], "a gap must have positive duration"


@settings(max_examples=300)
@given(markers=markers, window=windows)
def test_complete_is_exactly_the_absence_of_gaps(markers, window):
    started_at, stopped_at = window
    coverage = compute_transcript_coverage(markers, started_at, stopped_at)

    assert coverage["complete"] is (coverage["gaps"] == [])
    # And the two readings of "nothing missing" agree.
    if coverage["complete"]:
        assert coverage["missing_s"] == 0.0


@settings(max_examples=300)
@given(window=windows)
def test_no_markers_is_always_complete(window):
    """The invariant this design exists for.

    Whatever the recording's shape, a session nobody interrupted is complete.
    No silence, no pause, no length of tail can make it partial, because none
    of those is evidence that transcription stopped.
    """
    started_at, stopped_at = window

    coverage = compute_transcript_coverage([], started_at, stopped_at)

    assert coverage["complete"] is True
    assert coverage["missing_s"] == 0.0


@settings(max_examples=200)
@given(
    resumes=st.lists(
        st.fixed_dictionaries(
            {
                "type": st.just("transcript.resumed"),
                "at": marker_times,
            }
        ),
        min_size=1,
        max_size=8,
    ),
    window=windows,
)
def test_resumes_alone_never_create_a_gap(resumes, window):
    """A resume with no interruption before it is not evidence of anything —
    it means transcription started, which is the normal case."""
    started_at, stopped_at = window

    coverage = compute_transcript_coverage(resumes, started_at, stopped_at)

    assert coverage["complete"] is True
