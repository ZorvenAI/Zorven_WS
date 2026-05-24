"""Hypothesis property tests for make_predict_fn (US-018)."""

import os

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.predict_fns.factory import make_predict_fn
from .conftest import MLFLOW_URI

ANTHROPIC_KEY = os.environ.get("POI_ANTHROPIC_API_KEY", "")

_prompt_names = st.sampled_from([
    "zorven-wf1-mra-system",
    "zorven-wf1-cia-analysis",
    "zorven-wf2-bpa-positioning",
    "zorven-wf3-cga-profiling",
])


class TestPredictFnProperties:
    @given(prompt_name=_prompt_names)
    @hyp_settings(max_examples=5)
    def test_factory_always_returns_callable(self, prompt_name):
        fn = make_predict_fn(
            prompt_name,
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_KEY or "placeholder",
        )
        assert callable(fn)

    @given(
        prompt_name=_prompt_names,
        model=st.sampled_from(["claude-sonnet-4-6", "claude-haiku-4-5"]),
    )
    @hyp_settings(max_examples=5)
    def test_factory_metadata_matches(self, prompt_name, model):
        fn = make_predict_fn(
            prompt_name, model=model,
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_KEY or "placeholder",
        )
        assert fn.prompt_name == prompt_name
        assert fn.model == model

    def test_missing_prompt_returns_string(self):
        fn = make_predict_fn(
            "__test_prop_nope_xyz",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_KEY or "placeholder",
        )
        result = fn()
        assert isinstance(result, str)
        assert result == ""
