"""Hypothesis property tests for golden datasets (US-026)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.datasets.golden_seed import GOLDEN_EXAMPLES
from app.registries.prompt_catalog import AGENT_PORTS


# Use sampled_from to test properties across all examples
example_strategy = st.sampled_from(GOLDEN_EXAMPLES)


class TestGoldenDatasetProperties:
    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_all_context_keys_prefixed(self, example):
        for key in example.input_context:
            assert key.startswith("context."), f"Key '{key}' not prefixed"

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_source_in_allowed_set(self, example):
        assert example.source in {"manual", "synthetic", "mined", "adversarial"}

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_agent_code_valid(self, example):
        assert example.agent_code.lower() in {a.lower() for a in AGENT_PORTS}

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_prompt_name_follows_convention(self, example):
        assert example.prompt_name.startswith("zorven-wf")

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_expected_output_non_empty(self, example):
        assert isinstance(example.expected_output, str)
        assert len(example.expected_output.strip()) > 0

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_metadata_has_industry(self, example):
        assert "industry" in example.metadata_extra

    @given(example_strategy)
    @settings(max_examples=100, deadline=None)
    def test_input_context_non_empty(self, example):
        assert len(example.input_context) > 0
