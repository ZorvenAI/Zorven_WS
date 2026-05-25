"""Unit tests for golden evaluation datasets (US-026).

Validates the ~260 golden examples meet AC-1 through AC-4.
"""

from collections import Counter

from app.datasets.golden_seed import GOLDEN_EXAMPLES, GoldenExample
from app.registries.prompt_catalog import AGENT_PORTS

VALID_SOURCES = {"manual", "synthetic", "mined", "adversarial"}
REQUIRED_METADATA = {"industry", "brand_maturity"}

# §6.2 minimum coverage per agent
MIN_COVERAGE = {
    "cga": 20,
    "coa": 20,
    "bpa": 20,
    "bpv": 20,
    "caa": 15,
    "adpub": 15,
    "ila": 15,
    "mra": 15,
    "cia": 15,
    "apa": 15,
    "tcia": 15,
    "voca": 15,
    "baa": 15,
    "nta": 15,
    "bsa": 15,
}


class TestGoldenDatasetCoverage:
    """AC-1: Coverage per agent meets §6.2 minimums."""

    def test_total_count(self):
        assert len(GOLDEN_EXAMPLES) >= 260

    def test_per_agent_minimums(self):
        counts_raw = Counter(e.agent_code for e in GOLDEN_EXAMPLES)
        # Normalize to lowercase for comparison
        counts = Counter()
        for code, n in counts_raw.items():
            counts[code.lower()] += n
        for agent, minimum in MIN_COVERAGE.items():
            actual = counts.get(agent.lower(), 0)
            assert (
                actual >= minimum
            ), f"Agent {agent}: {actual} examples < minimum {minimum}"

    def test_all_15_agents_represented(self):
        agents = {e.agent_code.lower() for e in GOLDEN_EXAMPLES}
        for agent in AGENT_PORTS:
            assert agent.lower() in agents, f"Agent {agent} has no golden examples"

    def test_examples_are_golden_example_instances(self):
        for e in GOLDEN_EXAMPLES:
            assert isinstance(e, GoldenExample)


class TestIndustryVerticals:
    """AC-2: Examples span at least 10 industry verticals."""

    def test_at_least_10_industries(self):
        industries = {
            e.metadata_extra.get("industry")
            for e in GOLDEN_EXAMPLES
            if e.metadata_extra.get("industry")
        }
        assert (
            len(industries) >= 10
        ), f"Only {len(industries)} industries: {sorted(industries)}"

    def test_industries_are_strings(self):
        for e in GOLDEN_EXAMPLES:
            industry = e.metadata_extra.get("industry")
            if industry is not None:
                assert isinstance(industry, str)
                assert len(industry) > 0


class TestContextKeys:
    """AC-3: Each example uses context.* keys."""

    def test_all_keys_start_with_context(self):
        for i, e in enumerate(GOLDEN_EXAMPLES):
            for key in e.input_context:
                assert key.startswith("context."), (
                    f"Example {i} ({e.prompt_name}): key '{key}' "
                    "does not start with 'context.'"
                )

    def test_input_context_is_dict(self):
        for e in GOLDEN_EXAMPLES:
            assert isinstance(e.input_context, dict)

    def test_input_context_non_empty(self):
        for e in GOLDEN_EXAMPLES:
            assert len(e.input_context) > 0, f"{e.prompt_name}: input_context is empty"

    def test_shared_context_keys_present(self):
        """Most examples should have brand_name and industry."""
        with_brand = sum(
            1 for e in GOLDEN_EXAMPLES if "context.brand_name" in e.input_context
        )
        assert with_brand >= len(GOLDEN_EXAMPLES) * 0.8


class TestSourceLabels:
    """AC-4: source = manual | synthetic | mined | adversarial."""

    def test_all_sources_valid(self):
        for e in GOLDEN_EXAMPLES:
            assert (
                e.source in VALID_SOURCES
            ), f"{e.prompt_name}: invalid source '{e.source}'"

    def test_source_distribution(self):
        counts = Counter(e.source for e in GOLDEN_EXAMPLES)
        # Manual should be the largest
        assert counts["manual"] >= counts["synthetic"]
        assert counts["manual"] >= counts["mined"]
        assert counts["manual"] >= counts["adversarial"]

    def test_all_source_types_present(self):
        sources = {e.source for e in GOLDEN_EXAMPLES}
        assert sources == VALID_SOURCES

    def test_adversarial_examples_exist(self):
        adversarial = [e for e in GOLDEN_EXAMPLES if e.source == "adversarial"]
        assert len(adversarial) >= 5


class TestExpectedOutput:
    """Expected output validation."""

    def test_all_have_expected_output(self):
        for e in GOLDEN_EXAMPLES:
            assert isinstance(e.expected_output, str)
            assert (
                len(e.expected_output.strip()) > 0
            ), f"{e.prompt_name}: expected_output is empty"


class TestMetadataExtra:
    """Metadata quality checks."""

    def test_required_metadata_fields(self):
        for e in GOLDEN_EXAMPLES:
            assert isinstance(e.metadata_extra, dict)
            for field in REQUIRED_METADATA:
                assert (
                    field in e.metadata_extra
                ), f"{e.prompt_name}: missing metadata field '{field}'"

    def test_brand_maturity_values(self):
        valid_maturity = {"new", "emerging", "established"}
        for e in GOLDEN_EXAMPLES:
            maturity = e.metadata_extra.get("brand_maturity")
            if maturity:
                assert maturity in valid_maturity

    def test_all_three_maturities_represented(self):
        maturities = {e.metadata_extra.get("brand_maturity") for e in GOLDEN_EXAMPLES}
        assert "new" in maturities
        assert "emerging" in maturities
        assert "established" in maturities


class TestPromptNames:
    """Prompt name validation."""

    def test_all_prompt_names_non_empty(self):
        for e in GOLDEN_EXAMPLES:
            assert isinstance(e.prompt_name, str)
            assert len(e.prompt_name) > 0

    def test_prompt_names_follow_convention(self):
        for e in GOLDEN_EXAMPLES:
            assert e.prompt_name.startswith(
                "zorven-wf"
            ), f"Invalid prompt name: {e.prompt_name}"

    def test_agent_codes_valid(self):
        valid_agents = {a.lower() for a in AGENT_PORTS}
        for e in GOLDEN_EXAMPLES:
            assert (
                e.agent_code.lower() in valid_agents
            ), f"Invalid agent_code: {e.agent_code}"

    def test_no_exact_duplicates(self):
        """No two examples have identical prompt_name + input_context."""
        import json

        seen = set()
        for e in GOLDEN_EXAMPLES:
            key = (e.prompt_name, json.dumps(e.input_context, sort_keys=True))
            assert key not in seen, f"Duplicate example: {e.prompt_name}"
            seen.add(key)
