"""
Management command to check prompt cache health.

Usage:
    python manage.py cache_health
"""

import logging

from django.core.management.base import BaseCommand

from ai_services.prompt_cache import get_cache_metrics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Display prompt cache hit/miss metrics and health status"

    def handle(self, *args, **options):
        metrics = get_cache_metrics()
        g = metrics["global"]

        hits = g["hits"]
        misses = g["misses"]
        total = g["total"]
        rate = g["hit_rate_percent"]
        health = g["health"]

        if total == 0:
            self.stdout.write(
                self.style.WARNING("No prompt cache activity yet (0 hits, 0 misses).")
            )
            return

        # Color-coded output
        if health == "healthy":
            style = self.style.SUCCESS
            logger.info(
                "Prompt cache healthy: %.1f%% hit rate (%d/%d)",
                rate,
                hits,
                total,
            )
        elif health == "warning":
            style = self.style.WARNING
            logger.warning(
                "Prompt cache warning: %.1f%% hit rate (%d/%d)",
                rate,
                hits,
                total,
            )
        else:
            style = self.style.ERROR
            logger.error(
                "Prompt cache critical: %.1f%% hit rate (%d/%d)",
                rate,
                hits,
                total,
            )

        self.stdout.write(
            style(
                f"Prompt Cache Health: {health.upper()}\n"
                f"  Hit rate:  {rate:.1f}%\n"
                f"  Hits:      {hits}\n"
                f"  Misses:    {misses}\n"
                f"  Total:     {total}"
            )
        )
