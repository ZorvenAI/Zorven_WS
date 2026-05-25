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
        version = int(pv.version)
        logger.info("Registered prompt: %s v%d", name, version)
        return PromptInfo(
            name=name,
            version=version,
            template=template,
            tags=tags or {},
        )

    def get_prompt(self, name: str) -> Optional[PromptInfo]:
        """Get the latest version of a prompt. Returns None if not found."""
        try:
            versions = self.client.search_prompt_versions(name)
            if not versions:
                return None
            latest = max(versions, key=lambda v: int(v.version))
            return PromptInfo(
                name=name,
                version=int(latest.version),
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
                return pv.template
            else:
                versions = self.client.search_prompt_versions(name)
                if versions:
                    latest = max(versions, key=lambda v: int(v.version))
                    return latest.template
                return None
        except Exception:
            return None

    def set_prompt_state(self, name: str, version: int, state: str) -> None:
        """Update the state tag on a prompt version."""
        self.client.set_prompt_version_tag(name, version, "state", state)
        logger.info("State updated: %s v%d → %s", name, version, state)

    def get_prompt_by_state(
        self,
        name: str,
        state: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[PromptInfo]:
        """Find a prompt version with a specific state tag.

        Searches versions from latest to earliest.
        """
        try:
            versions = self.client.search_prompt_versions(name)
            for pv in versions:
                tags = pv.tags or {}
                if tags.get("state") != state:
                    continue
                if tenant_id and tags.get("tenant_id") != tenant_id:
                    continue
                if not tenant_id and tags.get("tenant_id"):
                    continue
                return PromptInfo(
                    name=name,
                    version=int(pv.version),
                    template=pv.template,
                    tags=tags,
                )
            return None
        except Exception:
            return None
