#!/usr/bin/env python
"""Clean up stale user_1 tenant from failed backfill run."""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from tenants.models import Tenant, Domain  # noqa: E402
from django.db import connection  # noqa: E402

# Clean up any tenants with schema_name starting with "user_"
stale = Tenant.objects.filter(schema_name__startswith="user_")
for t in stale:
    print(f"Removing stale tenant id={t.id} schema={t.schema_name}")
    Domain.objects.filter(tenant=t).delete()
    t.auto_drop_schema = False
    t.delete()

# Drop any stale schemas
with connection.cursor() as c:
    c.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE 'user_%'"
    )
    for row in c.fetchall():
        schema = row[0]
        print(f"Dropping stale schema: {schema}")
        c.execute(f'DROP SCHEMA "{schema}" CASCADE')

print("Cleanup done.")
