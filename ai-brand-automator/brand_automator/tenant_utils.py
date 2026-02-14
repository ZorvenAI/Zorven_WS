"""
Shared multi-tenancy utilities for background workers.

This module provides helpers for Celery tasks and Kafka consumers
that run outside Django's request/response cycle and therefore
lack the automatic tenant context provided by middleware.

The platform uses FK-based shared-schema multi-tenancy
(``auto_create_schema = False``). All tables live in the ``public``
schema — tenant isolation is enforced via ``tenant_id`` foreign-key
filters, **not** via PostgreSQL schema switching.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_tenant_pk(tenant_id: Optional[str] = None) -> Optional[int]:
    """Parse a tenant_id string into an integer primary key.

    Background workers (Kafka consumers, Celery tasks) receive tenant
    identifiers as strings.  This helper validates and converts the
    value so it can be used in ORM ``filter(tenant_id=…)`` calls.

    Args:
        tenant_id: Tenant primary key as a string, ``"public"``, or
            ``None``/empty when the caller has no tenant context.

    Returns:
        The integer pk suitable for ``Model.objects.filter(tenant_id=pk)``,
        or ``None`` when the input is missing / invalid / ``"public"``.
    """
    if not tenant_id or tenant_id == "public":
        return None
    try:
        return int(tenant_id)
    except (ValueError, TypeError):
        logger.warning("Invalid tenant_id %r — cannot convert to int", tenant_id)
        return None
