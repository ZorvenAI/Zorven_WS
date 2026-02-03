"""
DLP Adapter - Google Cloud DLP implementation of DLPPort.

Handles PII detection and redaction for the curation pipeline.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from django.conf import settings

from media_curation.ports.dlp_port import DLPPort, PIIFinding, RedactionResult
from media_curation.domain.models import TenantConfig
from media_curation.domain.exceptions import DLPError


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=4)

# Default PII types to detect
DEFAULT_INFO_TYPES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "CREDIT_CARD_NUMBER",
    "PERSON_NAME",
    "STREET_ADDRESS",
]


class CloudDLPAdapter(DLPPort):
    """
    Google Cloud DLP adapter implementing DLPPort.

    Uses the google-cloud-dlp library for PII detection and redaction.
    Provides async wrappers around synchronous DLP client methods.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        default_info_types: Optional[list[str]] = None,
    ):
        """
        Initialize the DLP adapter.

        Args:
            project_id: GCP project ID (uses settings if not provided)
            credentials_path: Path to service account JSON file
            default_info_types: Default PII types to detect
        """
        # Lazy import to avoid issues when google-cloud-dlp is not installed
        try:
            from google.cloud import dlp_v2

            self._dlp_available = True
        except ImportError:
            self._dlp_available = False
            logger.warning("google-cloud-dlp not installed, using mock mode")
            self.client = None
            return

        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)
        self.default_info_types = default_info_types or DEFAULT_INFO_TYPES

        if credentials_path:
            self.client = dlp_v2.DlpServiceClient.from_service_account_json(
                credentials_path
            )
        else:
            # Use Application Default Credentials
            self.client = dlp_v2.DlpServiceClient()

        self.parent = f"projects/{self.project_id}"

        logger.info(
            "Cloud DLP adapter initialized",
            extra={"project_id": self.project_id},
        )

    def _get_info_types_config(
        self, tenant_config: Optional[TenantConfig] = None
    ) -> list[dict]:
        """Get info types configuration from tenant config or defaults."""
        if tenant_config and tenant_config.dlp_info_types:
            info_types = tenant_config.dlp_info_types
        else:
            info_types = self.default_info_types

        return [{"name": it} for it in info_types]

    def _likelihood_to_string(self, likelihood) -> str:
        """Convert DLP likelihood enum to string."""
        likelihood_map = {
            0: "LIKELIHOOD_UNSPECIFIED",
            1: "VERY_UNLIKELY",
            2: "UNLIKELY",
            3: "POSSIBLE",
            4: "LIKELY",
            5: "VERY_LIKELY",
        }
        return likelihood_map.get(likelihood, "UNKNOWN")

    async def detect_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
    ) -> list[PIIFinding]:
        """Detect PII in text without redacting."""
        if not self._dlp_available:
            # Mock mode: return empty findings
            logger.debug("DLP not available, returning empty findings")
            return []

        def _detect():
            from google.cloud import dlp_v2

            try:
                # Build the inspect config
                inspect_config = dlp_v2.InspectConfig(
                    info_types=self._get_info_types_config(tenant_config),
                    min_likelihood=dlp_v2.Likelihood.POSSIBLE,
                    include_quote=True,
                )

                # Build the content item
                item = dlp_v2.ContentItem(value=text)

                # Call the API
                response = self.client.inspect_content(
                    request={
                        "parent": self.parent,
                        "inspect_config": inspect_config,
                        "item": item,
                    }
                )

                # Convert findings to our model
                findings = []
                if response.result.findings:
                    for finding in response.result.findings:
                        findings.append(
                            PIIFinding(
                                info_type=finding.info_type.name,
                                likelihood=self._likelihood_to_string(
                                    finding.likelihood
                                ),
                                start_offset=finding.location.byte_range.start,
                                end_offset=finding.location.byte_range.end,
                                quote=finding.quote if finding.quote else None,
                            )
                        )

                return findings

            except Exception as e:
                logger.error(f"DLP detect error: {e}")
                raise DLPError(f"PII detection failed: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _detect)

    async def redact_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
        replacement_token: str = "[REDACTED]",
    ) -> RedactionResult:
        """Detect and redact PII from text."""
        if not self._dlp_available:
            # Mock mode: return original text
            logger.debug("DLP not available, returning original text")
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                findings=[],
                findings_count=0,
                redaction_applied=False,
            )

        def _redact():
            from google.cloud import dlp_v2

            try:
                # Build the inspect config
                info_types = self._get_info_types_config(tenant_config)
                inspect_config = dlp_v2.InspectConfig(
                    info_types=info_types,
                    min_likelihood=dlp_v2.Likelihood.POSSIBLE,
                    include_quote=True,
                )

                # Build the deidentify config with replacement
                deidentify_config = dlp_v2.DeidentifyConfig(
                    info_type_transformations=dlp_v2.InfoTypeTransformations(
                        transformations=[
                            dlp_v2.InfoTypeTransformations.InfoTypeTransformation(
                                info_types=info_types,
                                primitive_transformation=dlp_v2.PrimitiveTransformation(
                                    replace_config=dlp_v2.ReplaceValueConfig(
                                        new_value=dlp_v2.Value(
                                            string_value=replacement_token
                                        )
                                    )
                                ),
                            )
                        ]
                    )
                )

                # Build the content item
                item = dlp_v2.ContentItem(value=text)

                # First, detect to get findings
                inspect_response = self.client.inspect_content(
                    request={
                        "parent": self.parent,
                        "inspect_config": inspect_config,
                        "item": item,
                    }
                )

                findings = []
                if inspect_response.result.findings:
                    for finding in inspect_response.result.findings:
                        findings.append(
                            PIIFinding(
                                info_type=finding.info_type.name,
                                likelihood=self._likelihood_to_string(
                                    finding.likelihood
                                ),
                                start_offset=finding.location.byte_range.start,
                                end_offset=finding.location.byte_range.end,
                                quote=finding.quote if finding.quote else None,
                            )
                        )

                # If no findings, return original
                if not findings:
                    return RedactionResult(
                        original_text=text,
                        redacted_text=text,
                        findings=[],
                        findings_count=0,
                        redaction_applied=False,
                    )

                # Redact the text
                deidentify_response = self.client.deidentify_content(
                    request={
                        "parent": self.parent,
                        "deidentify_config": deidentify_config,
                        "inspect_config": inspect_config,
                        "item": item,
                    }
                )

                return RedactionResult(
                    original_text=text,
                    redacted_text=deidentify_response.item.value,
                    findings=findings,
                    findings_count=len(findings),
                    redaction_applied=True,
                )

            except Exception as e:
                logger.error(f"DLP redact error: {e}")
                raise DLPError(f"PII redaction failed: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _redact)

    async def is_healthy(self) -> bool:
        """Check if DLP service is available."""
        if not self._dlp_available:
            return False

        def _check():
            try:
                # List a single info type as health check
                self.client.list_info_types(request={"parent": self.parent})
                return True
            except Exception as e:
                logger.warning(f"DLP health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
