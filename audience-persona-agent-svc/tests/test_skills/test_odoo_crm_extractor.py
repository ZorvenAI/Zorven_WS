"""Tests for SKL-APA-05c: Odoo CRM Customer Extractor."""

from unittest.mock import AsyncMock

from app.skills.odoo_crm_customer_extractor import OdooCRMCustomerExtractor
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_odoo(customer_count=15):
    client = AsyncMock()
    customers = [
        {
            "id": i,
            "name": f"Company {i}",
            "industry_id": [1, "Technology"],
            "country_id": [1, "United States"],
            "category_id": [],
            "company_type": "company",
        }
        for i in range(customer_count)
    ]
    leads = [
        {
            "id": 100 + i,
            "partner_id": [i, f"Company {i}"],
            "stage_id": [1, "Won"],
            "expected_revenue": 10000,
        }
        for i in range(min(customer_count, 5))
    ]
    orders = [
        {
            "id": 200 + i,
            "partner_id": [i, f"Company {i}"],
            "amount_total": 5000.0,
        }
        for i in range(min(customer_count, 3))
    ]
    client.search_read = AsyncMock(side_effect=[customers, leads, orders])
    return client


def _mock_redis(cached=None):
    rm = AsyncMock()
    rm.get_odoo_crm_cache = AsyncMock(return_value=cached)
    rm.set_odoo_crm_cache = AsyncMock()
    return rm


class TestOdooCRMCustomerExtractor:
    async def test_meta(self):
        skill = OdooCRMCustomerExtractor(AsyncMock(), AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-05c"

    async def test_execute_sufficient_data(self):
        odoo = _mock_odoo(customer_count=15)
        redis = _mock_redis()
        skill = OdooCRMCustomerExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data["has_sufficient_data"] is True
        assert result.data["crm_data"]["customer_count"] == 15

    async def test_execute_insufficient_data(self):
        odoo = _mock_odoo(customer_count=5)
        redis = _mock_redis()
        skill = OdooCRMCustomerExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data["has_sufficient_data"] is False

    async def test_cache_hit(self):
        cached = {
            "context": "cached",
            "sources": [],
            "crm_data": {},
            "segments": [],
            "has_sufficient_data": True,
        }
        redis = _mock_redis(cached=cached)
        skill = OdooCRMCustomerExtractor(AsyncMock(), redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data == cached

    async def test_odoo_error(self):
        odoo = AsyncMock()
        odoo.search_read = AsyncMock(side_effect=Exception("Timeout"))
        redis = _mock_redis()
        skill = OdooCRMCustomerExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is False
