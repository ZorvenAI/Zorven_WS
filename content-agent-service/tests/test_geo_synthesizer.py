"""Tests for GEOSynthesizer — citation extraction from research data."""

from app.logic.geo_synthesizer import GEOSynthesizer


class TestCitationExtraction:
    """Citation extraction and mapping tests."""

    def test_extracts_citations_from_research(self) -> None:
        synthesizer = GEOSynthesizer()
        research = {
            "sources": [
                {"title": "Source A", "url": "https://a.com"},
                {"title": "Source B", "url": "https://b.com"},
            ],
            "findings": [
                "Finding one about markets.",
                "Finding two about competitors.",
            ],
        }
        citations = synthesizer.synthesize(research, [])
        assert len(citations) >= 2
        assert citations[0].claim == "Finding one about markets."
        assert citations[0].source_title == "Source A"
        assert citations[0].source_url == "https://a.com"

    def test_maps_findings_to_sources(self) -> None:
        synthesizer = GEOSynthesizer()
        research = {
            "sources": [{"title": "Only Source", "url": "https://only.com"}],
            "findings": ["Finding 1", "Finding 2", "Finding 3"],
        }
        citations = synthesizer.synthesize(research, [])
        # All findings should map to the single source (cycling)
        for c in citations:
            if c.claim.startswith("Finding"):
                assert c.source_url == "https://only.com"

    def test_max_10_citations(self) -> None:
        synthesizer = GEOSynthesizer()
        research = {
            "sources": [
                {"title": f"Source {i}", "url": f"https://s{i}.com"}
                for i in range(15)
            ],
            "findings": [f"Finding {i}" for i in range(15)],
        }
        citations = synthesizer.synthesize(research, [])
        assert len(citations) <= 10

    def test_handles_empty_research_data(self) -> None:
        synthesizer = GEOSynthesizer()
        citations = synthesizer.synthesize({}, [])
        assert citations == []

    def test_handles_missing_previous_outputs(self) -> None:
        synthesizer = GEOSynthesizer()
        citations = synthesizer.synthesize(
            {"sources": [], "findings": []}, []
        )
        assert citations == []

    def test_handles_findings_without_sources(self) -> None:
        synthesizer = GEOSynthesizer()
        research = {
            "sources": [],
            "findings": ["A finding without a source"],
        }
        citations = synthesizer.synthesize(research, [])
        assert len(citations) >= 1
        assert citations[0].claim == "A finding without a source"
