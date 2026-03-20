import logging

from django.core.cache import cache
from django.core.management.base import BaseCommand

from analytics.brand_affinity import BrandAffinityVerifier
from analytics.extractors import PIPELINE_EXTRACTORS
from analytics.models import MetricDefinition, MetricSnapshot
from analytics.rollups import update_rollups
from orchestration.models import AnalysisJob

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill analytics from existing completed AnalysisJob records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without writing data",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max jobs to process (0 = all)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        jobs = (
            AnalysisJob.objects.filter(
                status=AnalysisJob.Status.COMPLETED,
                result_data__isnull=False,
            )
            .select_related("manifest", "tenant")
            .order_by("created_at")
        )

        if limit:
            jobs = jobs[:limit]

        definitions = {d.metric_name: d for d in MetricDefinition.objects.all()}

        total = 0
        extracted = 0
        skipped = 0
        excluded = 0

        for job in jobs.iterator():
            total += 1
            redis_key = f"analytics:extracted:{job.id}"

            # Idempotency
            if cache.get(redis_key):
                skipped += 1
                continue

            # Resolve pipeline
            pipeline_id = (
                job.manifest.pipeline_id
                if job.manifest
                else (job.input_context or {}).get("pipeline_id", "unknown")
            )

            if pipeline_id not in PIPELINE_EXTRACTORS:
                skipped += 1
                if not dry_run:
                    cache.set(redis_key, "unmapped", 86400)
                continue

            if not job.tenant:
                skipped += 1
                if not dry_run:
                    cache.set(redis_key, "no_tenant", 86400)
                continue

            # Brand affinity verification
            try:
                verifier = BrandAffinityVerifier(job.tenant)
                should_extract, _reason, _scores = verifier.verify(job)
            except Exception as e:
                logger.warning("Affinity check failed for job %s: %s", job.id, e)
                should_extract = True

            if not should_extract:
                excluded += 1
                if not dry_run:
                    cache.set(redis_key, "excluded", 86400)
                continue

            # Extract
            extractor = PIPELINE_EXTRACTORS[pipeline_id]
            try:
                metrics = extractor.extract(job)
            except Exception as e:
                logger.warning("Extraction failed for job %s: %s", job.id, e)
                skipped += 1
                continue

            if not metrics:
                skipped += 1
                if not dry_run:
                    cache.set(redis_key, "no_metrics", 86400)
                continue

            # Clamp values
            for m in metrics:
                defn = definitions.get(m.metric_name)
                if defn:
                    m.metric_value = max(
                        defn.value_range_min,
                        min(defn.value_range_max, m.metric_value),
                    )

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Job {job.job_id}: "
                    f"{len(metrics)} metrics from {pipeline_id}"
                )
            else:
                MetricSnapshot.objects.bulk_create(metrics, ignore_conflicts=True)
                try:
                    update_rollups(job.tenant, pipeline_id, metrics)
                except Exception as e:
                    logger.warning("Rollup update failed for job %s: %s", job.id, e)
                cache.set(redis_key, "extracted", 86400)

            extracted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {total} jobs processed, "
                f"{extracted} extracted, {skipped} skipped, "
                f"{excluded} excluded by brand affinity"
            )
        )
