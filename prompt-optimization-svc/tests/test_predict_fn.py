"""Unit tests for make_predict_fn factory (US-018)."""

from unittest.mock import MagicMock, patch

from app.predict_fns.factory import make_predict_fn


class TestMakePredictFnFactory:
    """Test factory creation and configuration."""

    @patch("app.predict_fns.factory.mlflow")
    @patch("app.predict_fns.factory.anthropic")
    def test_factory_returns_callable(self, mock_anthropic, mock_mlflow):
        fn = make_predict_fn("zorven-wf1-mra-system")
        assert callable(fn)

    @patch("app.predict_fns.factory.mlflow")
    @patch("app.predict_fns.factory.anthropic")
    def test_factory_attaches_metadata(self, mock_anthropic, mock_mlflow):
        fn = make_predict_fn("zorven-wf1-mra-system", model="claude-haiku-4-5")
        assert fn.prompt_name == "zorven-wf1-mra-system"
        assert fn.model == "claude-haiku-4-5"

    @patch("app.predict_fns.factory.mlflow")
    @patch("app.predict_fns.factory.anthropic")
    def test_default_model(self, mock_anthropic, mock_mlflow):
        fn = make_predict_fn("test")
        assert fn.model == "claude-sonnet-4-6"


class TestPredictFnExecution:
    """Test predict_fn behavior."""

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_loads_prompt_from_mlflow(self, mock_mlflow, mock_anthropic):
        """AC-1: Factory loads prompt via mlflow.genai.load_prompt."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "Formatted prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Response")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf1-mra-system")
        result = fn(context_brand_name="Nike")

        mock_mlflow.genai.load_prompt.assert_called_once_with(
            "prompts:/zorven-wf1-mra-system/production",
            allow_missing=True,
        )
        assert result == "Response"

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_formats_template_with_kwargs(self, mock_mlflow, mock_anthropic):
        """AC-2: Factory formats with kwargs."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "Analyze Nike in sportswear"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Analysis")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf1-mra-system")
        fn(context_brand_name="Nike", context_industry="sportswear")

        # Underscores converted to dots
        mock_pv.format.assert_called_once()
        call_kwargs = mock_pv.format.call_args[1]
        assert call_kwargs["context.brand.name"] == "Nike" or \
               call_kwargs.get("context_brand_name") == "Nike" or \
               "Nike" in str(call_kwargs)

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_calls_anthropic_api(self, mock_mlflow, mock_anthropic):
        """AC-2: Factory invokes Anthropic Messages API."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "Formatted prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Claude response")]
        mock_client.messages.create.return_value = mock_msg
        mock_anthropic.Anthropic.return_value = mock_client

        fn = make_predict_fn("test", model="claude-sonnet-4-6")
        fn()

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs["messages"][0]["content"] == "Formatted prompt"

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_returns_first_content_block_text(
        self, mock_mlflow, mock_anthropic
    ):
        """AC-3: Returns the model's first content block text."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        block1 = MagicMock()
        block1.text = "First block text"
        block2 = MagicMock()
        block2.text = "Second block text"

        mock_msg = MagicMock()
        mock_msg.content = [block1, block2]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("test")
        result = fn()
        assert result == "First block text"


class TestPredictFnAgentPrompts:
    """AC-4: Factory works with CGA and MRA prompts."""

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_works_with_cga_prompt(self, mock_mlflow, mock_anthropic):
        """AC-4: Factory works with CGA prompt name."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "CGA prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Creative output")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf3-cga-profiling")
        result = fn(context_brand_name="TestBrand")
        assert result == "Creative output"
        assert fn.prompt_name == "zorven-wf3-cga-profiling"

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_works_with_mra_prompt(self, mock_mlflow, mock_anthropic):
        """AC-4: Factory works with MRA prompt name."""
        mock_pv = MagicMock()
        mock_pv.format.return_value = "MRA prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Market research")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("zorven-wf1-mra-planning")
        result = fn(context_brand_name="Acme", context_industry="tech")
        assert result == "Market research"
        assert fn.prompt_name == "zorven-wf1-mra-planning"


class TestPredictFnErrorHandling:
    """Test graceful error handling."""

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_mlflow_load_failure_returns_empty(
        self, mock_mlflow, mock_anthropic
    ):
        mock_mlflow.genai.load_prompt.return_value = None

        fn = make_predict_fn("nonexistent")
        result = fn()
        assert result == ""

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_anthropic_failure_returns_empty(
        self, mock_mlflow, mock_anthropic
    ):
        mock_pv = MagicMock()
        mock_pv.format.return_value = "prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_anthropic.Anthropic.return_value.messages.create.side_effect = (
            Exception("API error")
        )

        fn = make_predict_fn("test")
        result = fn()
        assert result == ""

    @patch("app.predict_fns.factory.anthropic")
    @patch("app.predict_fns.factory.mlflow")
    def test_empty_content_returns_empty(self, mock_mlflow, mock_anthropic):
        mock_pv = MagicMock()
        mock_pv.format.return_value = "prompt"
        mock_mlflow.genai.load_prompt.return_value = mock_pv

        mock_msg = MagicMock()
        mock_msg.content = []
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_msg
        )

        fn = make_predict_fn("test")
        result = fn()
        assert result == ""
