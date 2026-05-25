"""Unit tests for synthetic context generator (US-027)."""

import pytest

from .conftest import requires_anthropic


class TestSyntheticContextGeneratorInit:
    """Generator initialization tests."""

    def test_empty_api_key_raises(self):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        with pytest.raises(ValueError, match="API key is required"):
            SyntheticContextGenerator(api_key="")

    def test_none_api_key_raises(self):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        with pytest.raises(ValueError, match="API key is required"):
            SyntheticContextGenerator(api_key=None)

    def test_whitespace_api_key_raises(self):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        with pytest.raises(ValueError, match="API key is required"):
            SyntheticContextGenerator(api_key="   ")

    def test_valid_api_key_succeeds(self):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key="sk-ant-test-key")
        assert gen.client is not None


class TestSyntheticContextGenerate:
    """Generation tests — require Anthropic API."""

    @requires_anthropic
    def test_generate_returns_context_and_profile(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        context, profile = gen.generate(
            industry="SaaS/Technology",
            brand_maturity="new",
            objective="Drive trial signups",
        )
        assert isinstance(context, dict)
        assert isinstance(profile, dict)

    @requires_anthropic
    def test_context_has_required_keys(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        context, _ = gen.generate(
            industry="E-commerce/Retail",
            brand_maturity="emerging",
            objective="Increase online sales",
        )
        assert "context_brand_name" in context
        assert "context_industry" in context
        assert "context_target_audience" in context
        assert "context_brand_voice" in context
        assert "context_product_description" in context

    @requires_anthropic
    def test_all_context_keys_prefixed(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        context, _ = gen.generate(
            industry="Healthcare/Wellness",
            brand_maturity="established",
            objective="Retain existing customers",
        )
        for key in context:
            assert key.startswith("context_"), f"Key '{key}' not prefixed"

    @requires_anthropic
    def test_profile_has_required_fields(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        _, profile = gen.generate(
            industry="Financial Services",
            brand_maturity="new",
            objective="Build brand awareness",
        )
        assert isinstance(profile["brand_name"], str)
        assert len(profile["brand_name"]) > 0
        assert "product_description" in profile
        assert "target_audience" in profile
        assert "brand_voice" in profile

    @requires_anthropic
    def test_brand_name_is_fictional(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        _, profile = gen.generate(
            industry="SaaS/Technology",
            brand_maturity="new",
            objective="Launch new product",
        )
        real_brands = {
            "google",
            "apple",
            "microsoft",
            "amazon",
            "meta",
            "facebook",
            "salesforce",
            "hubspot",
            "stripe",
            "shopify",
        }
        assert profile["brand_name"].lower() not in real_brands

    @requires_anthropic
    def test_generate_example_returns_golden_example(self):
        from app.core.config import settings
        from app.datasets.golden_seed import GoldenExample
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        example = gen.generate_example(
            industry="Education/EdTech",
            brand_maturity="emerging",
            objective="Acquire students",
            prompt_name="zorven-wf1-mra-system",
            agent_code="mra",
        )
        assert isinstance(example, GoldenExample)
        assert example.source == "synthetic"
        assert example.agent_code == "mra"
        assert example.prompt_name == "zorven-wf1-mra-system"

    @requires_anthropic
    def test_generate_example_metadata(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        example = gen.generate_example(
            industry="Food & Beverage",
            brand_maturity="established",
            objective="Expand market share",
            prompt_name="zorven-wf2-bpa-positioning",
            agent_code="bpa",
        )
        assert example.metadata_extra["industry"] == "Food & Beverage"
        assert example.metadata_extra["brand_maturity"] == "established"
        assert example.metadata_extra["objective"] == "Expand market share"

    @requires_anthropic
    def test_generate_batch_returns_correct_count(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        tuples = [
            ("SaaS/Technology", "new", "Drive signups"),
            ("E-commerce/Retail", "emerging", "Increase sales"),
        ]
        examples, errors = gen.generate_batch(tuples=tuples)
        assert len(examples) == 2
        assert len(errors) == 0
        assert all(e.source == "synthetic" for e in examples)

    @requires_anthropic
    def test_context_industry_matches_input(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        context, _ = gen.generate(
            industry="Automotive",
            brand_maturity="new",
            objective="Launch EV brand",
        )
        assert context["context_industry"] == "Automotive"
