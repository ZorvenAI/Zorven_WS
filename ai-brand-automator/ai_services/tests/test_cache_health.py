"""
Tests for cache metrics endpoint and cache_health management command.
"""

import pytest
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
@pytest.mark.unit
class TestCacheMetricsEndpoint:
    """Tests for GET /api/v1/ai/cache-metrics/"""

    def url(self):
        return reverse("cache_metrics")

    def test_requires_auth(self, api_client):
        response = api_client.get(self.url())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_requires_admin(self, authenticated_client):
        response = authenticated_client.get(self.url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access(self, admin_client):
        response = admin_client.get(self.url())
        assert response.status_code == status.HTTP_200_OK
        assert "global" in response.data
        assert "hits" in response.data["global"]
        assert "misses" in response.data["global"]
        assert "health" in response.data["global"]

    def test_health_levels(self, admin_client):
        response = admin_client.get(self.url())
        assert response.status_code == status.HTTP_200_OK
        assert response.data["global"]["health"] in (
            "healthy",
            "warning",
            "critical",
        )


@pytest.mark.django_db
@pytest.mark.unit
class TestCacheHealthCommand:
    """Tests for the cache_health management command."""

    def test_command_runs_without_error(self):
        out = StringIO()
        call_command("cache_health", stdout=out)
        output = out.getvalue()
        # Should produce some output (either "No activity" or stats)
        assert len(output) > 0

    @patch("ai_services.management.commands.cache_health.get_cache_metrics")
    def test_command_shows_healthy(self, mock_metrics):
        mock_metrics.return_value = {
            "global": {
                "hits": 90,
                "misses": 10,
                "total": 100,
                "hit_rate_percent": 90.0,
                "health": "healthy",
            }
        }
        out = StringIO()
        call_command("cache_health", stdout=out)
        output = out.getvalue()
        assert "HEALTHY" in output
        assert "90.0%" in output

    @patch("ai_services.management.commands.cache_health.get_cache_metrics")
    def test_command_shows_warning(self, mock_metrics):
        mock_metrics.return_value = {
            "global": {
                "hits": 60,
                "misses": 40,
                "total": 100,
                "hit_rate_percent": 60.0,
                "health": "warning",
            }
        }
        out = StringIO()
        call_command("cache_health", stdout=out)
        output = out.getvalue()
        assert "WARNING" in output

    @patch("ai_services.management.commands.cache_health.get_cache_metrics")
    def test_command_shows_critical(self, mock_metrics):
        mock_metrics.return_value = {
            "global": {
                "hits": 20,
                "misses": 80,
                "total": 100,
                "hit_rate_percent": 20.0,
                "health": "critical",
            }
        }
        out = StringIO()
        call_command("cache_health", stdout=out)
        output = out.getvalue()
        assert "CRITICAL" in output

    @patch("ai_services.management.commands.cache_health.get_cache_metrics")
    def test_command_no_activity(self, mock_metrics):
        mock_metrics.return_value = {
            "global": {
                "hits": 0,
                "misses": 0,
                "total": 0,
                "hit_rate_percent": 0.0,
                "health": "critical",
            }
        }
        out = StringIO()
        call_command("cache_health", stdout=out)
        output = out.getvalue()
        assert "No prompt cache activity" in output
