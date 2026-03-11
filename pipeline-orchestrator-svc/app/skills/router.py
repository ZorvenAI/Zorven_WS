"""Skill router — selects and packages skills for each pipeline node."""

import logging
from typing import Any

from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Persona-specific Odoo node IDs all share the same skill set as
# the generic ``odoo_worker``.  This mapping lets the registry look
# up skills using the canonical agent ID.
_ODOO_NODE_ALIASES: dict[str, str] = {
    "odoo_sales_crm": "odoo_worker",
    "odoo_finance": "odoo_worker",
    "odoo_inventory": "odoo_worker",
    "odoo_hr": "odoo_worker",
    "odoo_marketing": "odoo_worker",
    "odoo_manufacturing": "odoo_worker",
}


class SkillRouter:
    """Selects skills for pipeline nodes and packages them for injection.

    Called by the JobExecutor before dispatching each external node.
    Returns a skill_context dict that gets merged into the node's config.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def skill_count(self) -> int:
        return self._registry.skill_count

    def resolve_skills_for_node(
        self,
        node_id: str,
        prompt: str,
        max_skills: int = 3,
    ) -> dict[str, Any]:
        """Resolve skills for a pipeline node and return config additions.

        Returns a dict with skill_context (str) and skill_names (list).
        Returns empty dict if no skills match (fail-open).
        """
        lookup_id = _ODOO_NODE_ALIASES.get(node_id, node_id)
        matched = self._registry.match_skills(lookup_id, prompt, max_skills=max_skills)

        if not matched:
            return {}

        skill_names = [s.meta.name for s in matched]
        logger.info(
            "Node %s matched %d skill(s): %s",
            node_id,
            len(matched),
            ", ".join(skill_names),
        )

        return {
            "skill_context": self._registry.format_skill_context(matched),
            "skill_names": skill_names,
        }
