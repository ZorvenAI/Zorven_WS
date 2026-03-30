"""Tests for NTA Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    AvailabilityResult,
    ExecuteRequest,
    NameCandidate,
    NameScore,
    NamingBrief,
    NTAResponse,
    Tagline,
    TenantContext,
)


class TestExecuteRequest:
    """Test request model validation."""

    def test_minimal_request(self):
        req = ExecuteRequest()
        assert req.input_prompt == ""
        assert req.input_context == {}
        assert req.previous_outputs == {}

    def test_full_request(self):
        req = ExecuteRequest(
            input_prompt="Generate brand names",
            input_context={"company": "TestCo"},
            tenant_context={"tenant_id": "t1", "user_role": "EDITOR"},
            config={"max_candidates": 10},
            previous_outputs={"market_research": {}},
        )
        assert req.input_prompt == "Generate brand names"
        # tenant_context can be either dict or TenantContext model
        assert isinstance(req.tenant_context, (dict, TenantContext))

    def test_tenant_context_as_model(self):
        tc = TenantContext(tenant_id="t1", company_name="TestCo")
        req = ExecuteRequest(tenant_context=tc)
        assert req.tenant_context.tenant_id == "t1"


class TestNameScore:
    """Test score validation."""

    def test_default_scores(self):
        score = NameScore()
        assert score.linguistic == 0.0
        assert score.overall == 0.0

    def test_valid_scores(self):
        score = NameScore(linguistic=85.5, memorability=90, availability=75.2)
        assert score.linguistic == 85.5

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            NameScore(linguistic=101)

    def test_negative_score(self):
        with pytest.raises(ValidationError):
            NameScore(memorability=-1)


class TestAvailabilityResult:
    """Test availability result model."""

    def test_defaults_are_none(self):
        avail = AvailabilityResult()
        assert avail.domain_com is None
        assert avail.twitter is None
        assert avail.trademark_clear is None
        assert avail.trademark_notes == ""

    def test_full_availability(self):
        avail = AvailabilityResult(
            domain_com=True,
            domain_io=False,
            twitter=True,
            instagram=False,
            linkedin=None,
            trademark_clear=True,
            trademark_notes="No conflicts found",
        )
        assert avail.domain_com is True
        assert avail.trademark_notes == "No conflicts found"


class TestNameCandidate:
    """Test name candidate model."""

    def test_minimal_candidate(self):
        c = NameCandidate(name="TestBrand")
        assert c.name == "TestBrand"
        assert c.shortlisted is False
        assert c.scores.overall == 0.0

    def test_full_candidate(self):
        c = NameCandidate(
            name="Voltara",
            rationale="Voltage + aura",
            naming_type="coined",
            scores=NameScore(linguistic=85, memorability=90, overall=87),
            availability=AvailabilityResult(domain_com=True),
            shortlisted=True,
        )
        assert c.scores.linguistic == 85
        assert c.availability.domain_com is True


class TestTagline:
    """Test tagline model."""

    def test_minimal_tagline(self):
        t = Tagline(tagline="Power Every Journey")
        assert t.tagline == "Power Every Journey"
        assert t.name == ""
        assert t.memorability_score == 0.0

    def test_score_validation(self):
        with pytest.raises(ValidationError):
            Tagline(tagline="Test", memorability_score=101)


class TestNamingBrief:
    """Test naming brief model."""

    def test_defaults(self):
        brief = NamingBrief()
        assert brief.recommended_name == ""
        assert brief.next_steps == []

    def test_full_brief(self):
        brief = NamingBrief(
            recommended_name="Voltara",
            recommended_tagline="Power Every Journey",
            rationale="Strong coined name",
            next_steps=["Register domain", "File trademark"],
        )
        assert len(brief.next_steps) == 2


class TestNTAResponse:
    """Test full response model."""

    def test_defaults(self):
        resp = NTAResponse()
        assert resp.name_candidates == []
        assert resp.confidence_score == 0.0
        assert resp.wf1_context_used is False
        assert resp.execution_time_ms == 0

    def test_full_response(self):
        resp = NTAResponse(
            query="Generate names",
            name_candidates=[
                NameCandidate(name="Voltara"),
            ],
            shortlisted_names=["Voltara"],
            taglines=[Tagline(tagline="Power Every Journey")],
            naming_brief=NamingBrief(recommended_name="Voltara"),
            confidence_score=0.85,
            wf1_context_used=True,
            bpa_context_used=True,
            bpv_context_used=True,
            execution_time_ms=1500,
        )
        assert len(resp.name_candidates) == 1
        assert resp.shortlisted_names == ["Voltara"]

    def test_dict_candidates_accepted(self):
        """Response accepts both NameCandidate objects and raw dicts."""
        resp = NTAResponse(
            name_candidates=[
                {"name": "TestBrand", "rationale": "Test"},
            ],
            taglines=[
                {"tagline": "Test Line", "name": "TestBrand"},
            ],
        )
        assert len(resp.name_candidates) == 1
