"""
DLP (Data Loss Prevention) Port.

Abstract interface for PII detection and redaction.
Concrete implementation: DLPAdapter (Google Cloud DLP).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from media_curation.domain.models import TenantConfig


@dataclass
class PIIFinding:
    """A single PII finding in text."""

    info_type: str  # EMAIL_ADDRESS, PHONE_NUMBER, etc.
    likelihood: str  # VERY_UNLIKELY to VERY_LIKELY
    start_offset: int
    end_offset: int
    quote: Optional[str] = None  # The actual PII text (for debugging)


@dataclass
class RedactionResult:
    """Result of PII redaction operation."""

    original_text: str
    redacted_text: str
    findings: list[PIIFinding]
    findings_count: int
    redaction_applied: bool

    @property
    def has_pii(self) -> bool:
        """Check if any PII was found."""
        return self.findings_count > 0


class DLPPort(ABC):
    """
    Abstract interface for PII detection and redaction.

    Implementations should handle:
    - Detection of various PII types (email, phone, SSN, etc.)
    - Custom PII patterns per tenant
    - Redaction with configurable replacement tokens
    """

    @abstractmethod
    async def detect_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
    ) -> list[PIIFinding]:
        """
        Detect PII in text without redacting.

        Args:
            text: Text to scan for PII
            tenant_config: Tenant-specific PII configuration

        Returns:
            List of PII findings
        """
        pass

    @abstractmethod
    async def redact_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
        replacement_token: str = "[REDACTED]",
    ) -> RedactionResult:
        """
        Detect and redact PII from text.

        Args:
            text: Text to redact
            tenant_config: Tenant-specific PII configuration
            replacement_token: Token to replace PII with

        Returns:
            RedactionResult with original and redacted text
        """
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if DLP service is available."""
        pass
