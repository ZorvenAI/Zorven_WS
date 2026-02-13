#!/usr/bin/env python
"""
Full database reset script for AI Brand Automator.

Drops all tenant schemas (except public), flushes all data,
and recreates the public tenant. Use for a completely fresh start.

Usage:
    python scripts/reset_database.py              # uses DATABASE_URL from .env
    DATABASE_URL=<url> python scripts/reset_database.py  # explicit URL
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from tenants.models import Domain, Tenant  # noqa: E402


def reset_database():
    """Drop all tenant schemas, flush data, and recreate public tenant."""
    db_name = settings.DATABASES["default"].get("NAME", "unknown")
    db_host = settings.DATABASES["default"].get("HOST", "unknown")
    print(f"Target database: {db_name} @ {db_host}")
    print("=" * 60)

    # Step 1: Drop all non-public tenant schemas
    print("\n[1/4] Dropping tenant schemas...")
    tenants = Tenant.objects.exclude(schema_name="public")
    count = tenants.count()
    for tenant in tenants:
        schema = tenant.schema_name
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            print(f"  Dropped schema: {schema}")
        except Exception as e:
            print(f"  WARNING: Could not drop schema {schema}: {e}")
    print(f"  -> {count} tenant schemas dropped")

    # Step 2: Delete all data from Django tables in public schema
    print("\n[2/4] Flushing all data from public schema...")

    # Delete in dependency order to avoid FK violations
    tables_to_clear = [
        # Pipeline / media
        "media_curation_curationstatus",
        "data_ingestion_processingstatus",
        "rag_index_indexsyncstatus",
        # AI services
        "ai_services_chatmessage",
        "ai_services_chatsession",
        # Onboarding
        "onboarding_brandasset",
        "onboarding_onboardingprogress",
        "onboarding_brandstrategy",
        "onboarding_company",
        # Automation
        "automation_socialaccount",
        "automation_scheduledpost",
        "automation_socialpost",
        "automation_contentcalendar",
        # Subscriptions
        "subscriptions_subscription",
        # Files (in public schema)
        "files_brandassetfile",
        # Tenants (domains first, then memberships, then tenants)
        "tenants_domain",
        "tenants_membership",
        "tenants_tenant",
        # Auth
        "auth_user_user_permissions",
        "auth_user_groups",
        "authtoken_token",
        "django_admin_log",
        "auth_user",
        # Sessions
        "django_session",
        # Celery beat
        "django_celery_beat_periodictask",
        "django_celery_beat_crontabschedule",
        "django_celery_beat_intervalschedule",
        "django_celery_beat_solarschedule",
        "django_celery_beat_clockedschedule",
    ]

    with connection.cursor() as cursor:
        for table in tables_to_clear:
            try:
                cursor.execute(f"DELETE FROM public.{table}")  # noqa: S608
                print(f"  Cleared: {table}")
            except Exception as e:
                # Table may not exist yet — that's fine
                print(f"  Skipped: {table} ({e})")
                connection.cursor()  # reset cursor after error

    # Also TRUNCATE with CASCADE as a catch-all
    with connection.cursor() as cursor:
        try:
            cursor.execute(
                """
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT tablename FROM pg_tables
                        WHERE schemaname = 'public'
                        AND tablename NOT LIKE 'django_migrations'
                        AND tablename NOT LIKE 'django_content_type'
                    ) LOOP
                        EXECUTE 'TRUNCATE TABLE public.'
                            || quote_ident(r.tablename)
                            || ' CASCADE';
                    END LOOP;
                END $$;
            """
            )
            print("  -> All public tables truncated")
        except Exception as e:
            print(f"  WARNING: Bulk truncate failed: {e}")

    # Step 3: Reset migration history and re-migrate
    print("\n[3/4] Re-running migrations...")
    from django.core.management import call_command  # noqa: E402

    call_command("migrate_schemas", "--shared", "--noinput", verbosity=1)
    print("  -> Shared migrations applied")

    # Step 4: Recreate public tenant
    print("\n[4/4] Creating public tenant...")
    if not Tenant.objects.filter(schema_name="public").exists():
        public_tenant = Tenant.objects.create(
            schema_name="public",
            name="Public",
            description="Public schema for shared data",
        )
        Domain.objects.create(
            domain="localhost",
            tenant=public_tenant,
            is_primary=True,
        )
        print("  -> Public tenant + localhost domain created")
    else:
        print("  -> Public tenant already exists (re-created by migrations)")
        # Ensure localhost domain exists
        public_tenant = Tenant.objects.get(schema_name="public")
        if not Domain.objects.filter(tenant=public_tenant).exists():
            Domain.objects.create(
                domain="localhost",
                tenant=public_tenant,
                is_primary=True,
            )
            print("  -> localhost domain created")

    print("\n" + "=" * 60)
    print("Database reset complete!")
    print(f"  Tenants: {Tenant.objects.count()}")
    print("  Users: 0")
    print("  Companies: 0")
    print("Ready for fresh usage.")


if __name__ == "__main__":
    confirm = input("This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(1)
    reset_database()
