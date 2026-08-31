"""L-04: Tests for the tenant prompt scaffold signal."""

import pytest
from unittest.mock import patch, MagicMock
from django.db import connection

from tenants.models import Tenant


@pytest.fixture
def tenant_factory(db):
    """Factory that creates a tenant (fires post_save signal)."""
    connection.set_schema_to_public()
    counter = [0]

    def _create(**overrides):
        counter[0] += 1
        defaults = {
            "name": f"Scaffold Test {counter[0]}",
            "slug": f"scaffold-test-{counter[0]}",
        }
        defaults.update(overrides)
        return Tenant.objects.create(**defaults)

    return _create


@pytest.mark.django_db
class TestScaffoldTenantSignal:
    """scaffold_tenant_prompts signal fires on tenant creation."""

    @patch("tenants.signals.requests.post")
    @patch("tenants.signals.decouple_config")
    def test_signal_calls_poi_on_create(self, mock_config, mock_post, tenant_factory):
        mock_config.side_effect = lambda key, **kw: {
            "POI_AUTO_SCAFFOLD": True,
            "POI_SERVICE_URL": "http://poi:8110",
            "GCS_AUTO_PROVISION": False,
            "VERTEX_AI_AUTO_PROVISION": False,
        }.get(key, kw.get("default", ""))
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"scaffolded": 9, "skipped": 0}
        mock_post.return_value = mock_resp

        tenant_factory()

        calls = [c for c in mock_post.call_args_list if "scaffold-tenant" in str(c)]
        assert len(calls) == 1
        assert "scaffold-tenant" in str(calls[0])

    @patch("tenants.signals.requests.post")
    @patch("tenants.signals.decouple_config")
    def test_signal_skips_when_disabled(self, mock_config, mock_post, tenant_factory):
        mock_config.side_effect = lambda key, **kw: {
            "POI_AUTO_SCAFFOLD": False,
            "POI_SERVICE_URL": "http://poi:8110",
            "GCS_AUTO_PROVISION": False,
            "VERTEX_AI_AUTO_PROVISION": False,
        }.get(key, kw.get("default", ""))

        tenant_factory()

        scaffold_calls = [
            c for c in mock_post.call_args_list if "scaffold-tenant" in str(c)
        ]
        assert len(scaffold_calls) == 0

    @patch("tenants.signals.requests.post")
    @patch("tenants.signals.decouple_config")
    def test_signal_skips_on_update(self, mock_config, mock_post, tenant_factory):
        mock_config.side_effect = lambda key, **kw: {
            "POI_AUTO_SCAFFOLD": True,
            "POI_SERVICE_URL": "http://poi:8110",
            "GCS_AUTO_PROVISION": False,
            "VERTEX_AI_AUTO_PROVISION": False,
        }.get(key, kw.get("default", ""))
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"scaffolded": 9, "skipped": 0}
        mock_post.return_value = mock_resp

        tenant = tenant_factory()
        mock_post.reset_mock()

        tenant.name = "Updated Name"
        tenant.save()

        scaffold_calls = [
            c for c in mock_post.call_args_list if "scaffold-tenant" in str(c)
        ]
        assert len(scaffold_calls) == 0

    @patch("tenants.signals.requests.post")
    @patch("tenants.signals.decouple_config")
    def test_signal_swallows_errors(self, mock_config, mock_post, tenant_factory):
        mock_config.side_effect = lambda key, **kw: {
            "POI_AUTO_SCAFFOLD": True,
            "POI_SERVICE_URL": "http://poi:8110",
            "GCS_AUTO_PROVISION": False,
            "VERTEX_AI_AUTO_PROVISION": False,
        }.get(key, kw.get("default", ""))
        mock_post.side_effect = ConnectionError("boom")

        tenant = tenant_factory()
        assert tenant.pk is not None
