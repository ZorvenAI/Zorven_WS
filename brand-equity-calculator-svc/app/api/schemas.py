"""Pydantic request/response models for the brand equity calculator."""

from pydantic import BaseModel, Field


class BrandEquityRequest(BaseModel):
    """Input form data for brand equity calculation."""

    company_name: str = Field(
        ..., min_length=1, max_length=200, description="Company name"
    )
    address: str = Field(default="", max_length=500, description="Company address")
    website: str = Field(default="", max_length=500, description="Company website URL")
    industry_type: str = Field(
        ..., min_length=1, max_length=100, description="Industry classification"
    )
    business_size: str = Field(
        ..., description="micro | small | medium | large | enterprise"
    )
    scope: str = Field(..., description="local | regional | national | global")


class DimensionScore(BaseModel):
    """A single ISO 20671 dimension score."""

    name: str = Field(..., description="Dimension name")
    score: int = Field(..., ge=0, le=100, description="Score 0-100")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight in overall score")
    rationale: str = Field(default="", description="Explanation of scoring")
    key_factors: list[str] = Field(
        default_factory=list, description="Key factors considered"
    )


class Competitor(BaseModel):
    """A competitor identified during analysis."""

    name: str = Field(..., description="Competitor company name")
    headquarters: str = Field(default="", description="Headquarters location / address")
    estimated_score: int = Field(
        ..., ge=0, le=100, description="Estimated brand equity score"
    )
    strengths: list[str] = Field(default_factory=list, description="Key strengths")
    weaknesses: list[str] = Field(default_factory=list, description="Key weaknesses")


class BrandEquityResponse(BaseModel):
    """Full brand equity evaluation result."""

    company_name: str
    overall_score: int = Field(
        ..., ge=0, le=100, description="Weighted overall brand equity score"
    )
    dimensions: list[DimensionScore] = Field(default_factory=list)
    competitors: list[Competitor] = Field(
        default_factory=list,
        description="Top competitors with estimated scores, strengths, and weaknesses",
    )
    formula_explanation: str = Field(
        default="", description="How the score was calculated"
    )
    derivation: str = Field(default="", description="Step-by-step score derivation")
    limitations: list[str] = Field(
        default_factory=list, description="Data and methodology limitations"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    methodology: str = Field(default="ISO 20671:2019", description="Standard used")


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
