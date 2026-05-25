"""Integration tests for synthetic context generator (US-027).

Requires real Anthropic API.
"""

from tests.conftest import requires_anthropic


@requires_anthropic
class TestSyntheticGeneratorIntegration:
    """Full generation tests with real Anthropic API."""

    def test_full_generate_returns_valid_profile(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        context, profile = gen.generate(
            industry="SaaS/Technology",
            brand_maturity="new",
            objective="Drive trial signups",
        )

        # Context has all required keys
        assert "context_brand_name" in context
        assert "context_industry" in context
        assert "context_target_audience" in context
        assert "context_brand_voice" in context
        assert "context_product_description" in context

        # Profile has all required fields
        assert isinstance(profile["brand_name"], str)
        assert len(profile["brand_name"]) > 0
        assert len(profile["product_description"]) > 0

    def test_generated_brand_is_fictional(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        _, profile = gen.generate(
            industry="E-commerce/Retail",
            brand_maturity="emerging",
            objective="Increase online sales",
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
            "nike",
            "adidas",
            "coca-cola",
            "pepsi",
            "walmart",
        }
        assert profile["brand_name"].lower() not in real_brands

    def test_batch_generates_correct_count(self):
        from app.core.config import settings
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
        examples, errors = gen.generate_batch(
            tuples=[
                ("Healthcare/Wellness", "new", "Patient acquisition"),
                ("Financial Services", "established", "Wealth management"),
            ],
        )
        assert len(examples) == 2
        assert len(errors) == 0
        assert all(e.source == "synthetic" for e in examples)
        assert all("context_brand_name" in e.input_context for e in examples)
