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
    model: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Callable[..., str]:
    """Create a predict function for GEPA optimization.

    Args:
        prompt_name: MLflow prompt name (§3.1 convention).
        model: Anthropic model ID.
        mlflow_tracking_uri: MLflow server URI (default from settings).
        anthropic_api_key: Anthropic API key (default from settings).
        max_tokens: Max tokens for Anthropic response.

    Returns:
        A callable(**kwargs) -> str that loads the prompt, formats it,
        calls Claude, and returns the first content block text.
    """
    model = model or settings.GEPA_MODEL_NAME
    max_tokens = max_tokens or settings.GEPA_MAX_TOKENS
    tracking_uri = mlflow_tracking_uri or settings.MLFLOW_TRACKING_URI
    api_key = anthropic_api_key or settings.ANTHROPIC_API_KEY

    # Set tracking URI for MLflow prompt loading
    mlflow.set_tracking_uri(tracking_uri)

    # Create Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    # Cache MlflowClient on the closure to avoid per-call overhead
    from mlflow.tracking import MlflowClient

    _mlflow_client = MlflowClient(tracking_uri)

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
            versions = _mlflow_client.search_prompt_versions(prompt_name)
            if not versions:
                logger.warning(
                    "Prompt '%s' not found in MLflow — returning empty",
                    prompt_name,
                )
                return ""
            latest_ver = max(
                versions, key=lambda v: int(v.version)
            ).version
            prompt_uri = f"prompts:/{prompt_name}/{latest_ver}"
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

            formatted_prompt = prompt_version.format(
                **formatted_kwargs, allow_partial=True
            )

            # AC-2: Invoke Anthropic Messages API
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": formatted_prompt}],
            )

            # AC-3: Return the model's first text content block
            if message.content and len(message.content) > 0:
                return next(
                    (b.text for b in message.content if b.type == "text"),
                    "",
                )

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
