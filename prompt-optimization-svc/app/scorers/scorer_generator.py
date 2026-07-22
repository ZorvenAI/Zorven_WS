"""Auto-generate baseline scorers from skill output_schema (US-054).

For each prompt in an optimization group, looks up the matching skill
via SkillRegistryReader, then uses BaselineScorerFactory to create
field-presence, max-length, enum-compliance, and schema-completeness
scorers from the skill's output_schema.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def generate_baseline_scorers(
    group_name: str,
    skill_reader=None,
) -> list[Callable]:
    """Generate baseline scorers for all prompts in an optimization group.

    Args:
        group_name: Optimization group name (e.g., "wf1-discovery-pipeline").
        skill_reader: Optional SkillRegistryReader instance. Created if None.

    Returns:
        Flat list of scorer callables generated from output schemas.
        Returns empty list if no skills match or on any error.
    """
    from app.registries.optimization_groups import get_group
    from app.scorers.baseline.factory import BaselineScorerFactory
    from app.services.skill_registry_reader import SkillRegistryReader

    reader = skill_reader or SkillRegistryReader()
    factory = BaselineScorerFactory(reader)

    group = get_group(group_name)
    scorers: list[Callable] = []

    for i, prompt_name in enumerate(group.prompt_names):
        agent_code = group.agent_codes[min(i, len(group.agent_codes) - 1)]
        try:
            prompt_scorers = factory.create_scorers_for_prompt(agent_code, prompt_name)
            if prompt_scorers:
                scorers.extend(prompt_scorers)
                logger.debug(
                    "Generated %d baseline scorers for %s/%s",
                    len(prompt_scorers),
                    agent_code,
                    prompt_name,
                )
        except Exception as exc:
            logger.warning(
                "Failed to generate baseline scorers for %s/%s: %s",
                agent_code,
                prompt_name,
                exc,
            )

    return scorers
