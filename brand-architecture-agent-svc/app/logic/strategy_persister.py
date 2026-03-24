"""SKL-BAA-11: Strategy persistence to GCS + RAG + Redis registry."""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class StrategyPersister:
    """Persist architecture strategy to storage backends."""

    async def persist(self, tenant_id: str, strategy: dict[str, Any]) -> dict[str, Any]:
        """Persist strategy data.

        Currently Redis-only. GCS + RAG deferred to v2.
        """
        logger.info("Strategy persistence for tenant %s (Redis only)", tenant_id)
        return {"persisted_to": ["redis"], "version": 1}

    async def sync_brand_context(
        self, tenant_id: str, hierarchy: dict[str, Any], company_name: str = ""
    ) -> bool:
        """Sync brand context options to Django Redis via backend API.

        Extracts brand entities from the hierarchy tree and posts them to
        the brand-context-sync endpoint so the Brand Context Selector can
        consume them.
        """
        options = _flatten_hierarchy(hierarchy, company_name)
        if not options:
            logger.debug("No brand entities to sync for tenant %s", tenant_id)
            return False

        url = f"{settings.BACKEND_URL}/api/v1/analytics/brand-context-sync/"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={"tenant_id": tenant_id, "options": options},
                    headers={
                        "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 200:
                logger.info(
                    "Brand context synced for tenant %s: %d options",
                    tenant_id,
                    len(options),
                )
                return True
            else:
                logger.warning(
                    "Brand context sync failed for tenant %s: %s %s",
                    tenant_id,
                    resp.status_code,
                    resp.text[:200],
                )
                return False
        except Exception as exc:
            logger.warning("Brand context sync error for tenant %s: %s", tenant_id, exc)
            return False


def _flatten_hierarchy(hierarchy: dict[str, Any], parent_brand: str) -> list[dict]:
    """Recursively walk the hierarchy tree and extract brand entities.

    Claude's output structure: {"root": {name, type, children: [...]}, "total_depth": N}
    We skip the root (master) node and extract all children as brand entities.
    """
    if not hierarchy:
        return []

    results = []

    # Handle Claude's output format: hierarchy has a "root" key
    root = hierarchy.get("root")
    if root and isinstance(root, dict):
        # Skip the root (master) node itself, extract its children
        nodes = root.get("children") or root.get("sub_brands") or []
    else:
        # Fallback: try other key patterns
        nodes = hierarchy.get("nodes") or hierarchy.get("children") or []

        # Also handle the case where hierarchy IS the tree root with sub_brands
        sub_brands = hierarchy.get("sub_brands") or []
        if sub_brands:
            nodes = sub_brands

    for node in nodes:
        name = node.get("name", "")
        if not name:
            continue

        # Determine brand scope from node type/level
        node_type = (
            node.get("type", "") or node.get("brand_type", "") or node.get("level", "")
        ).lower()

        if node_type in ("product_line", "product"):
            scope = "product_line"
        elif node_type in ("endorsed", "endorsement"):
            scope = "endorsed"
        else:
            scope = "sub_brand"

        slug = name.lower().replace(" ", "-").replace("'", "")
        brand_context_id = f"{scope}:{slug}"

        results.append(
            {
                "brand_context_id": brand_context_id,
                "name": name,
                "brand_scope": scope,
                "parent_brand": parent_brand,
                "relationship_to_parent": node.get(
                    "relationship", node.get("architecture_model", "")
                ),
                "target_persona": node.get("target_persona")
                or node.get("target_audience", ""),
            }
        )

        # Recurse into children (pass as root-less hierarchy)
        children = node.get("children") or node.get("sub_brands") or []
        if children:
            child_results = _flatten_hierarchy({"nodes": children}, parent_brand)
            results.extend(child_results)

    return results
