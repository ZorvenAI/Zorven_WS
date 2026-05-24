"""Universal predict_fn factory for GEPA optimization (§4.4).

Creates a callable that:
1. Loads a prompt from MLflow Prompt Registry
2. Formats the template with provided kwargs
3. Calls the Anthropic Messages API
4. Returns the model's first content block text

Usage:
    predict = make_predict_fn("zorven-wf1-mra-system")
    result = predict(context_brand_name="Nike", context_industry="sportswear")
"""

import logging
from typing import Any, Callable, Optional

import anthropic
import mlflow

from app.core.config import settings

logger = logging.getLogger(__name__)


def make_predict_fn(
    prompt_name: str,
    model: str = "claude-sonnet-4-6",
    mlflow_tracking_uri: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Callable[..., str]:
    """Create a predict function for GEPA optimization.

    Args:
        prompt_name: MLflow prompt name (§3.1 convention).
        model: Anthropic model ID.
        mlflow_tracking_uri: MLflow server URI (default from settings).
        anthropic_api_key: Anthropic API key (default from settings).
        max_tokens: Max tokens for Anthropic response.
        temperature: Sampling temperature.

    Returns:
        A callable(**kwargs) -> str that loads the prompt, formats it,
        calls Claude, and returns the first content block text.
    """
    tracking_uri = mlflow_tracking_uri or settings.MLFLOW_TRACKING_URI
    api_key = anthropic_api_key or settings.ANTHROPIC_API_KEY

    # Set tracking URI for MLflow prompt loading
    mlflow.set_tracking_uri(tracking_uri)

    # Create Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    def predict_fn(**kwargs: Any) -> str:
        """Load prompt, format, call Claude, return text.

        Args:
            **kwargs: Template variables (context_brand_name, etc.).
                      Underscores are converted to dots for {{context.brand_name}}.

        Returns:
            Model's first content block text, or empty string on error.
        """
        try:
            # AC-1: Load prompt from MLflow registry
            prompt_uri = f"prompts:/{prompt_name}/production"
            prompt_version = mlflow.genai.load_prompt(
                prompt_uri, allow_missing=True
            )

            if prompt_version is None:
                logger.warning(
                    "Prompt '%s' not found in MLflow — returning empty",
                    prompt_name,
                )
                return ""

            # AC-2: Format template with kwargs
            # Convert context_ prefix: context_brand_name → context.brand_name
            formatted_kwargs = {}
            for key, value in kwargs.items():
                if key.startswith("context_"):
                    # Only replace the first underscore after "context"
                    dot_key = "context." + key[len("context_"):]
                    formatted_kwargs[dot_key] = str(value)
                else:
                    formatted_kwargs[key] = str(value)

            formatted_prompt = prompt_version.format(**formatted_kwargs)

            # AC-2: Invoke Anthropic Messages API
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": formatted_prompt}],
            )

            # AC-3: Return the model's first content block text
            if message.content and len(message.content) > 0:
                return message.content[0].text

            return ""

        except Exception as exc:
            logger.exception(
                "predict_fn error for prompt '%s': %s", prompt_name, exc
            )
            return ""

    # Attach metadata for introspection
    predict_fn.prompt_name = prompt_name
    predict_fn.model = model
    predict_fn.mlflow_tracking_uri = tracking_uri

    return predict_fn
