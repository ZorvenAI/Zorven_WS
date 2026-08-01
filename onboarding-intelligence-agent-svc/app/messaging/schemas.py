"""Kafka payload models (Design §13.2).

The envelope is shared across every topic; only ``payload`` varies. Models are
Pydantic so a malformed message fails at the boundary rather than three calls
deep inside a handler.

``GoldenCandidate`` is defined here because §13.2 defines it, but its topic is
**not** provisioned by A-03 — that is L-02's, and an empty topic nobody
consumes is worse than no topic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SOURCE_AGENT = "onboarding-intelligence"
SCHEMA_VERSION = "1.0"


class MessageEnvelope(BaseModel):
    """Shared envelope for every Kafka message this service sends."""

    schema_version: str = SCHEMA_VERSION
    message_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    correlation_id: str
    source_agent: str = SOURCE_AGENT
    tenant_id: uuid.UUID
    session_id: uuid.UUID | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceManifest(BaseModel):
    """What a PROCESS run is being asked to read.

    The manifest hash is half of the idempotency key, so re-running over
    unchanged evidence returns the original job rather than writing twice.
    """

    recording_ids: list[str] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    manifest_hash: str


class ProcessOptions(BaseModel):
    force_rerun: bool = False
    language: str | None = None


class ProcessCommand(BaseModel):
    job_id: str
    session_id: uuid.UUID
    evidence_manifest: EvidenceManifest
    options: ProcessOptions = Field(default_factory=ProcessOptions)
    idempotency_key: str


class ProcessSummary(BaseModel):
    fields_written: int = 0
    key_count: int = 0
    secondary_count: int = 0
    dropped_ungrounded: int = 0
    conflicts: int = 0


class ErrorDetail(BaseModel):
    """Errors carry a code from the §18.4 taxonomy, not a free-text message."""

    error_code: str
    message: str
    recoverable: bool = False


class ProcessResult(BaseModel):
    job_id: str
    status: Literal["SUCCEEDED", "FAILED", "PARTIAL"]
    summary: ProcessSummary | None = None
    error: ErrorDetail | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    duration_ms: int = 0


class EscalationMessage(BaseModel):
    """SKL-OIA-14 output — a conflict or low-confidence case for a human."""

    escalation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    session_id: uuid.UUID | None = None
    reason_code: str
    field_name: str | None = None
    confidence: float | None = None
    requires_role: str = "Admin"


class GoldenCandidate(BaseModel):
    """Flywheel input consumed by prompt-optimization-svc (§17.3).

    Values are redacted and evidence is referenced by GCS path plus span,
    never inlined — the candidate stream is not a transcript store.
    """

    prompt_id: str
    prompt_version: str
    field_name: str
    input_evidence_ref: str
    extracted_value: str
    admin_final_value: str
    edit_distance: float
    classification: Literal["KEY", "SECONDARY"]
    accepted_without_edit: bool


class DeadLetter(BaseModel):
    """A message that exhausted its retries, kept with enough to triage it.

    §20: the DLQ is reviewed daily and the replay tool re-publishes with the
    same idempotency_key, which is what makes replay safe by construction.
    """

    original_topic: str
    original_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str
    error_message: str
    attempts: int
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str | None = None
