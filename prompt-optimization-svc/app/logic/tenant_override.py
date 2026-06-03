"""Tenant-specific prompt override management (§10.1, §11.1).

Allows tenants to register overrides that take precedence over
global production prompts. RBAC-restricted to OWNER role.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

TENANT_CACHE_KEY = "prompt:{name}:tenant:{tenant_id}"


async def create_tenant_override(
    prompt_name: str,
    tenant_id: str,
    template: str,
    mlflow_registry: Any = None,
    prompt_cache: Any = None,
    lifecycle_producer: Any = None,
) -> dict:
    """Create a tenant-specific prompt override.

    Registers the override in MLflow with TENANT_OVERRIDE state
    and caches it in Redis for fast resolution.

    Args:
        prompt_name: Base prompt name (e.g., "zorven-wf3-cga-system").
        tenant_id: Tenant identifier.
        template: Override prompt template text.
        mlflow_registry: MLflow prompt registry client.
        prompt_cache: Redis prompt cache manager.
        lifecycle_producer: Kafka lifecycle event producer.

    Returns:
        Dict with override info (prompt_name, tenant_id, version, state).
    """
    version = 0

    # Register in MLflow with TENANT_OVERRIDE state
    if mlflow_registry is not None:
        info = mlflow_registry.register_prompt(
            name=prompt_name,
            template=template,
            tags={
                "state": "TENANT_OVERRIDE",
                "tenant_id": tenant_id,
            },
        )
        version = info.version

    # Cache in Redis for fast resolution
    if prompt_cache is not None:
        try:
            r = await prompt_cache.connect()
            key = TENANT_CACHE_KEY.format(name=prompt_name, tenant_id=tenant_id)
            await r.set(key, template)
        except Exception as exc:
            logger.warning("Failed to cache tenant override: %s", exc)

    # Emit Kafka event
    if lifecycle_producer is not None:
        lifecycle_producer.send_lifecycle_event_sync(
            event_type="prompt.tenant_override.created",
            prompt_name=prompt_name,
            version=version,
            from_state="DRAFT",
            to_state="TENANT_OVERRIDE",
            tenant_id=tenant_id,
        )

    logger.info(
        "Tenant override created: %s tenant=%s v%d",
        prompt_name,
        tenant_id,
        version,
    )
    return {
        "prompt_name": prompt_name,
        "tenant_id": tenant_id,
        "version": version,
        "template": template,
        "state": "TENANT_OVERRIDE",
    }


async def delete_tenant_override(
    prompt_name: str,
    tenant_id: str,
    mlflow_registry: Any = None,
    prompt_cache: Any = None,
    lifecycle_producer: Any = None,
) -> bool:
    """Delete a tenant-specific prompt override (AC-3).

    Removes the cache entry and transitions the MLflow version
    to ARCHIVED.

    Returns:
        True if override was found and deleted.
    """
    found = False

    # Archive the MLflow version
    if mlflow_registry is not None:
        override = mlflow_registry.get_prompt_by_state(
            prompt_name, "TENANT_OVERRIDE", tenant_id=tenant_id
        )
        if override is not None:
            mlflow_registry.set_prompt_state(prompt_name, override.version, "ARCHIVED")
            found = True

    # Delete Redis cache key (AC-3)
    if prompt_cache is not None:
        try:
            r = await prompt_cache.connect()
            key = TENANT_CACHE_KEY.format(name=prompt_name, tenant_id=tenant_id)
            deleted = await r.delete(key)
            if deleted:
                found = True
        except Exception as exc:
            logger.warning("Failed to delete tenant cache: %s", exc)

    # Emit Kafka event
    if lifecycle_producer is not None and found:
        lifecycle_producer.send_lifecycle_event_sync(
            event_type="prompt.tenant_override.deleted",
            prompt_name=prompt_name,
            version=0,
            from_state="TENANT_OVERRIDE",
            to_state="ARCHIVED",
            tenant_id=tenant_id,
        )

    if found:
        logger.info(
            "Tenant override deleted: %s tenant=%s",
            prompt_name,
            tenant_id,
        )
    return found


async def get_tenant_override(
    prompt_name: str,
    tenant_id: str,
    mlflow_registry: Any = None,
) -> Optional[dict]:
    """Get a tenant-specific prompt override.

    Returns:
        Dict with override info, or None if not found.
    """
    if mlflow_registry is None:
        return None

    override = mlflow_registry.get_prompt_by_state(
        prompt_name, "TENANT_OVERRIDE", tenant_id=tenant_id
    )
    if override is None:
        return None

    return {
        "prompt_name": override.name,
        "tenant_id": tenant_id,
        "version": override.version,
        "template": override.template,
        "state": "TENANT_OVERRIDE",
    }
