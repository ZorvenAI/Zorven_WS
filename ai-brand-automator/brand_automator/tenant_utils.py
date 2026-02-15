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


def ensure_public_db_connection(close_existing: bool = True) -> None:
    """Force the database connection to the ``public`` schema.

    Long-running Kafka consumers and Celery workers suffer from two
    distinct problems when using ``django_tenants.postgresql_backend``:

    1. **Stale connections** — Neon's connection pooler drops idle
       connections well before Django's ``CONN_MAX_AGE`` (600 s), causing
       ``InterfaceError: cursor already closed``.

    2. **Cached search_path** — After a reconnect the
       ``DatabaseWrapper`` may skip the ``SET search_path`` call because
       ``search_path_set_schemas`` was not cleared, leaving the cursor
       on whatever search-path the pooler's new backend happens to have.

    Args:
        close_existing: When ``True`` (the default) the underlying
            database connection is closed first — guaranteeing a
            completely fresh connection on the next ORM call.
            Pass ``False`` on the *first* attempt when the connection
            may still be valid (e.g. in tests or short-lived workers)
            to avoid disrupting Django's test-transaction machinery.

    Calling this function before every ORM operation in a background
    worker guarantees that ``schema_name`` is ``public`` and
    ``search_path_set_schemas`` is ``None``, so the next ``_cursor()``
    call will execute ``SET search_path = 'public'``.
    """
    from django.db import connection

    if close_existing:
        connection.close()
    # set_schema_to_public() sets schema_name='public' and clears
    # the search-path cache so the next cursor call issues
    # SET search_path = 'public'.
    connection.set_schema_to_public()
