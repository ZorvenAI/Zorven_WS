"""#662 markers are written by production paths, not only by tests.

Review of #673 found that **nothing in production wrote**
``transcript.resumed``. The marker type existed, coverage consumed it, and
every test that exercised it put it in Redis by hand — so the unit and
integration suites were green while the only path that mattered was missing.
An interruption's gap therefore ran to the end of the recording even when STT
came straight back.

A test that fabricates its own input cannot catch an input nobody produces.
These assert that each marker has a writer in ``app/api/ws.py``, by inspecting
the module the way ``test_locking_is_tenant_scoped.py`` inspects the views
module, for the same class of reason: the mistake is invisible at runtime and
obvious in the source.

**What this does not do**, stated plainly rather than implied away: it does not
drive a socket, so it cannot prove the writes are reached under real frame
sequencing or that the marker lands in Redis. The ``TestClient`` harness from
``test_ws_handshake.py`` was tried first and control frames never reached
``_handle_control`` through it; diagnosing that is separate work. Runtime
behaviour of the markers is covered by
``tests/integration/test_transcript_markers_live.py`` against real Redis. What
is covered *here* is that production calls the writer at all. An end-to-end
socket test remains the right follow-up.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.api import ws

pytestmark = pytest.mark.unit

#: Whitespace-collapsed so a call wrapped across lines by the formatter still
#: matches. The first version of this file missed every call for that reason.
FLAT_SOURCE = " ".join(inspect.getsource(ws).split())


def calls_for(marker: str) -> list[str]:
    """Every ``record_marker("<marker>"...)`` call site in the module."""
    pattern = re.compile(r"record_marker\(\s*[\"']" + re.escape(marker) + r"[\"']")
    return pattern.findall(FLAT_SOURCE)


@pytest.mark.parametrize(
    "marker,why",
    [
        (
            "transcript.interrupted",
            "nothing would record that a dropped socket truncated the "
            "transcript, which is the whole of #662",
        ),
        (
            "transcript.resumed",
            "an interruption's gap would run to the end of the recording even "
            "when STT came straight back — the defect #673's review found",
        ),
        (
            "transcript.stopped",
            "completeness rests on this marker, so without a writer every "
            "recording would report coverage as 'not assessed'",
        ),
    ],
)
def test_each_marker_has_a_production_writer(marker, why):
    assert calls_for(marker), f"no production call writes {marker}: {why}"


def test_both_start_branches_resume():
    """``start`` has a multi-stream branch and a single-stream branch, and only
    one runs per recording. Marking just one would make coverage correct for
    single-mic meetings and silently wrong for every multi-mic one."""
    assert len(calls_for("transcript.resumed")) >= 2, (
        "only one resume writer found; the multi-stream and single-stream "
        "start paths each need their own"
    )


def test_the_interruption_is_conditional_on_transcription_running():
    """A marker written on every socket close — including a clean stop — would
    report every finished meeting as truncated."""
    assert (
        "was_transcribing" in FLAT_SOURCE
    ), "the teardown no longer computes whether transcription was running"
    assert re.search(
        r"if was_transcribing and session is not None: "
        r"await session\.record_marker\( [\"']transcript\.interrupted[\"']",
        FLAT_SOURCE,
    ), "the interrupted marker is no longer guarded by was_transcribing"
