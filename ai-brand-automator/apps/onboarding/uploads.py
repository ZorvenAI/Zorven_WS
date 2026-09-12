"""Resumable upload sessions for meeting audio (F-03, FR-REC-03).

Django mints the session; the browser uploads to it directly.

That split is what the requirements ask for. NFR-REL-01 says "the **client**
buffers locally and resumes upload; a crashed tab does not lose already-uploaded
segments", and `app/providers/storage.py` in the agent pairs resumable upload
with "signed URL issuance" — which only means anything if somebody else is doing
the uploading. Design §4.3 draws the spool as an arrow out of `ws.py` instead,
with the agent appending; the backlog rules that out by ordering, since F-03
blocks F-04 and the socket is the agent's only audio ingress. Raised on #555.

Django rather than the agent because Django owns BrandAsset, the landing
bucket, tenant scoping and the ingestion pipeline this audio has to join. The
agent has no GCS code at all.

**Resumable, not composed.** The card is explicit, and the reason is AC-2: a
resumable session is addressed by byte offset, so a chunk retried after a
network drop lands at the same offset instead of appending a second copy.
Composing many small objects makes "no duplication under retry" a problem you
have to solve rather than one the protocol solves.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)

#: AC-1's path. `_landing/` is the existing ingestion prefix, so recordings
#: ride the pipeline that already exists rather than growing a parallel one.
LANDING_TEMPLATE = "_landing/{tenant_id}/{token}_{recording_id}.opus"

#: What the browser records. Opus in a WebM or Ogg container, per F-02.
CONTENT_TYPE = "audio/webm"


class UploadSessionError(Exception):
    """A resumable session could not be created."""


def landing_path(recording) -> str:
    """Where this recording's object lands.

    The uuid is not decoration. Two recordings on the same session could
    otherwise collide if a row id were ever reused, and a landing path that
    collides silently overwrites somebody's meeting.
    """
    return LANDING_TEMPLATE.format(
        tenant_id=recording.tenant_id or "public",
        token=uuid.uuid4().hex[:12],
        recording_id=recording.pk,
    )


def create_resumable_session(recording, *, origin: str = "") -> tuple[str, str]:
    """Open a GCS resumable session and return ``(session_url, gcs_path)``.

    ``origin`` is passed to GCS so it returns the CORS headers the browser
    needs on its PUTs. Without it the upload fails in the browser with an
    opaque CORS error while working perfectly from curl, which is a bad
    afternoon.

    Raises :class:`UploadSessionError` rather than returning a sentinel: a
    caller that cannot tell "no session" from "empty session" will upload into
    the void, and the operator finds out when the recording is missing.
    """
    from files.services import GCSService

    service = GCSService()
    bucket = service.get_bucket()
    if bucket is None:
        # GCSService falls back to a null client when credentials are absent,
        # which is right for local development of unrelated features and
        # completely wrong here — there is nowhere for the audio to go.
        raise UploadSessionError(
            "Google Cloud Storage is not configured; audio cannot be uploaded."
        )

    path = landing_path(recording)
    blob = bucket.blob(path)
    try:
        session_url = blob.create_resumable_upload_session(
            content_type=CONTENT_TYPE,
            origin=origin or None,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        logger.warning(
            "resumable_session_failed",
            extra={"recording_id": recording.pk, "error": type(exc).__name__},
        )
        raise UploadSessionError(
            "Could not open an upload session with Google Cloud Storage."
        ) from exc

    return session_url, path


def degraded_message() -> str:
    """AC-3's operator-facing text, from configuration rather than code.

    §18.2 is the source of truth and says why: "user_message is part of the
    config rather than the code because these strings are the entire user
    experience of a failure". That file lives in the agent's image, which this
    process cannot read, so the value is mirrored here — and
    `test_uploads.py::test_the_degraded_message_matches_the_breaker_config`
    reads both files and fails if they drift.
    """
    return getattr(
        settings,
        "OIA_GCS_DEGRADED_MESSAGE",
        "Upload delayed — recording continues locally.",
    )
