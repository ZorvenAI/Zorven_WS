"""Pydantic models for Kafka message payloads."""

from pydantic import BaseModel


class TitlingEvent(BaseModel):
    """Event payload for auto-titling a chat session."""

    session_id: str  # UUID string
    session_pk: int
    tenant_id: str
    first_message: str
    first_response: str = ""  # optional, for extra context
