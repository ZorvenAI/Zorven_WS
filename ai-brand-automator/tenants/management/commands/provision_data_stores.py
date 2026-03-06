"""
Provision Vertex AI data stores for tenants.

Finds tenants with an empty ``vertex_ai_data_store_id`` and creates
a per-tenant data store (``prevision-{slug}``) via the Discovery Engine API.

Usage::

    python manage.py provision_data_stores            # dry-run
    python manage.py provision_data_stores --apply     # actually provision
"""

from django.core.management.base import BaseCommand

from tenants.models import Tenant
from tenants.services import TenantVertexAIService


class Command(BaseCommand):
    help = "Provision Vertex AI data stores for tenants missing one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually create data stores (default is dry-run).",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]

        tenants = (
            Tenant.objects.filter(vertex_ai_data_store_id="")
            .exclude(schema_name="public")
            .exclude(slug="")
        )

        total = tenants.count()
        if total == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "All tenants already have Vertex AI data stores configured."
                )
            )
            return

        mode = "DRY RUN" if dry_run else "APPLYING"
        self.stdout.write(
            f"Found {total} tenant(s) without Vertex AI data stores ({mode}):\n"
        )

        if dry_run:
            for t in tenants:
                self.stdout.write(f"  [{t.id}] {t.name} (slug={t.slug})")
                self.stdout.write(f"       -> would assign: prevision-{t.slug}")
            self.stdout.write(
                f"\nDry run complete. Re-run with --apply to provision {total} tenant(s)."
            )
            return

        service = TenantVertexAIService()
        success = 0
        errors = 0

        for t in tenants:
            try:
                self.stdout.write(
                    f"  Provisioning data store for [{t.id}] {t.name} ...",
                    ending=" ",
                )
                service.create_tenant_data_store(t)
                self.stdout.write(self.style.SUCCESS("OK"))
                success += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"FAILED ({exc})"))
                errors += 1

        self.stdout.write(
            f"\nDone: {success} succeeded, {errors} failed out of {total}."
        )
