"""
GEO Synthesizer — extracts and maps citations from research data.

Pure logic module (no AI calls). Reorganizes existing research data
from discovery-agent-svc into structured citations.
"""

import logging
from typing import Any

from app.api.schemas import Citation

logger = logging.getLogger(__name__)

MAX_CITATIONS = 10


class GEOSynthesizer:
    """Extracts citations from research data for GEO compliance."""

    def synthesize(
        self,
        research_data: dict[str, Any],
        findings: list[str],
    ) -> list[Citation]:
        """
        Extract citations from previous_outputs["web_research"].

        Maps findings to their source URLs.
        Returns max 10 citations.
        """
        sources = research_data.get("sources", [])
        raw_findings = research_data.get("findings", [])

        if not sources and not raw_findings:
            logger.debug("No research data to synthesize citations from")
            return []

        citations: list[Citation] = []

        # Map each finding to the nearest source
        for i, finding in enumerate(raw_findings[:MAX_CITATIONS]):
            finding_text = finding if isinstance(finding, str) else str(finding)

            # Pick corresponding source, or cycle through available sources
            if sources:
                source = sources[i % len(sources)]
                source_title = (
                    source.get("title", "")
                    if isinstance(source, dict)
                    else str(source)
                )
                source_url = (
                    source.get("url", "")
                    if isinstance(source, dict)
                    else ""
                )
            else:
                source_title = ""
                source_url = ""

            citations.append(
                Citation(
                    claim=finding_text,
                    source_title=source_title,
                    source_url=source_url,
                )
            )

        # If we have more sources than findings, add remaining sources
        if len(sources) > len(raw_findings):
            for source in sources[len(raw_findings): MAX_CITATIONS]:
                if len(citations) >= MAX_CITATIONS:
                    break
                source_title = (
                    source.get("title", "")
                    if isinstance(source, dict)
                    else str(source)
                )
                source_url = (
                    source.get("url", "")
                    if isinstance(source, dict)
                    else ""
                )
                citations.append(
                    Citation(
                        claim=f"Source: {source_title}",
                        source_title=source_title,
                        source_url=source_url,
                    )
                )

        # Also include any findings from the caller
        for finding in findings[:MAX_CITATIONS]:
            if len(citations) >= MAX_CITATIONS:
                break
            # Avoid duplicates
            existing_claims = {c.claim for c in citations}
            if finding not in existing_claims:
                citations.append(
                    Citation(
                        claim=finding,
                        source_title="Research Finding",
                        source_url="",
                    )
                )

        return citations[:MAX_CITATIONS]
