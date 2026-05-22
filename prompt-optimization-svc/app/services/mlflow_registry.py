"""MLflow Prompt Registry client for prompt CRUD operations."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)


@dataclass
class PromptInfo:
    """Registered prompt metadata."""

    name: str
    version: int
    template: str
    tags: dict[str, str]


class MLflowPromptRegistry:
    """Client for the MLflow Prompt Registry."""

    def __init__(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri
        self.client = MlflowClient(tracking_uri)

    def register_prompt(
        self,
        name: str,
        template: str,
        tags: Optional[dict[str, str]] = None,
    ) -> PromptInfo:
        """Register a prompt (creates new or adds version if exists).

        Returns PromptInfo with the registered version.
        """
        pv = self.client.register_prompt(
            name=name,
            template=template,
            tags=tags or {},
        )
        logger.info("Registered prompt: %s v%d", name, pv.version)
        return PromptInfo(
            name=name,
            version=pv.version,
            template=template,
            tags=tags or {},
        )

    def get_prompt(self, name: str) -> Optional[PromptInfo]:
        """Get the latest version of a prompt. Returns None if not found."""
        try:
            prompt = self.client.get_prompt(name)
            latest = self.client.get_prompt_version(name, prompt.latest_version)
            return PromptInfo(
                name=name,
                version=int(prompt.latest_version),
                template=latest.template,
                tags=latest.tags or {},
            )
        except Exception:
            return None

    def prompt_exists(self, name: str) -> bool:
        """Check if a prompt is already registered."""
        return self.get_prompt(name) is not None

    def list_prompts(self) -> list[str]:
        """List all registered prompt names."""
        prompts = self.client.search_prompts()
        return [p.name for p in prompts]

    def load_prompt_template(
        self, name: str, version: Optional[int] = None
    ) -> Optional[str]:
        """Load a prompt template by name and optional version."""
        try:
            if version:
                pv = self.client.get_prompt_version(name, version)
            else:
                prompt = self.client.get_prompt(name)
                pv = self.client.get_prompt_version(
                    name, prompt.latest_version
                )
            return pv.template
        except Exception:
            return None
