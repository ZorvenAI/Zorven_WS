"""Hypothesis property tests for make_predict_fn (US-018)."""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.predict_fns.factory import make_predict_fn


# Strategy: valid prompt names matching §3.1
_prompt_names = st.sampled_from([
    "zorven-wf1-mra-system",
    "zorven-wf1-cia-analysis",
    "zorven-wf2-bpa-positioning",
    "zorven-wf3-cga-profiling",
    "zorven-wf3-coa-optimization",
])

# Strategy: context variable dicts with string keys/values
_context_kwargs = st.dictionaries(
    keys=st.sampled_from([
        "context_brand_name",
        "context_industry",
        "context_target_audience",
        "context_query",
        "context_budget",
    ]),
    values=st.text(min_size=1, max_size=100),
    min_size=0,
    max_size=5,
)


class TestPredictFnProperties:
    """Hypothesis property-based tests for predict_fn."""

    @given(prompt_name=_prompt_names)
    @settings(max_examples=10)
    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_factory_always_returns_callable(
        self, mock_mlflow, mock_anthropic, prompt_name
    ):
        """For any valid prompt name, factory returns a callable."""
        fn = make_predict_fn(prompt_name)
        assert callable(fn)

    @given(kwargs=_context_kwargs)
    @settings(max_examples=20)
    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_predict_fn_always_returns_string(
        self, mock_mlflow, mock_anthropic, kwargs
    ):
        """For any valid kwargs, predict_fn returns a string."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "formatted"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="response")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf1-mra-system")
        result = fn(**kwargs)
        assert isinstance(result, str)

    @given(kwargs=_context_kwargs)
    @settings(max_examples=10)
    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_predict_fn_returns_non_empty_on_success(
        self, mock_mlflow, mock_anthropic, kwargs
    ):
        """When API succeeds, returned text is non-empty."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "formatted"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="non-empty response")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf1-mra-system")
        result = fn(**kwargs)
        assert len(result) > 0

    @given(kwargs=_context_kwargs)
    @settings(max_examples=10)
    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_predict_fn_returns_string_on_error(
        self, mock_mlflow, mock_anthropic, kwargs
    ):
        """On any error, predict_fn still returns a string (empty)."""
        mock_mlflow.genai.load_prompt.side_effect = Exception("fail")

        fn = make_predict_fn("test")
        result = fn(**kwargs)
        assert isinstance(result, str)
        assert result == ""

    @given(
        prompt_name=_prompt_names,
        model=st.sampled_from([
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-opus-4-6",
        ]),
    )
    @settings(max_examples=10)
    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_factory_metadata_matches_inputs(
        self, mock_mlflow, mock_anthropic, prompt_name, model
    ):
        """Factory metadata always matches the input parameters."""
        fn = make_predict_fn(prompt_name, model=model)
        assert fn.prompt_name == prompt_name
        assert fn.model == model
