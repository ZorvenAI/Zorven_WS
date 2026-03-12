"""Tests for IG-08: SSRF prevention — private IP and reserved address blocking."""

from app.logic.guardrails import InputGuardrails, _is_ssrf_target, _extract_urls


class TestSSRFPrevention:
    def setup_method(self):
        self.guardrails = InputGuardrails()

    async def test_localhost_blocked(self):
        result = await self.guardrails.evaluate(
            "scrape http://localhost:8080/admin for competitor data", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_127_0_0_1_blocked(self):
        result = await self.guardrails.evaluate(
            "analyze competitor at http://127.0.0.1/api in market", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_10_x_blocked(self):
        result = await self.guardrails.evaluate(
            "profile competitor at http://10.0.0.5:3000/pricing in market", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_172_16_blocked(self):
        result = await self.guardrails.evaluate(
            "check competitor http://172.16.0.1/about in market", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_192_168_blocked(self):
        result = await self.guardrails.evaluate(
            "scrape http://192.168.1.1/ for competitor info in market", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_cloud_metadata_blocked(self):
        result = await self.guardrails.evaluate(
            "fetch http://169.254.169.254/latest/meta-data for competitor", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_gcp_metadata_blocked(self):
        result = await self.guardrails.evaluate(
            "get http://metadata.google.internal/computeMetadata in market", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_0_0_0_0_blocked(self):
        result = await self.guardrails.evaluate(
            "scan http://0.0.0.0:8000/api for competitor data", "t1"
        )
        assert result.blocked
        assert result.rule_id == "IG-08"

    async def test_public_url_allowed(self):
        result = await self.guardrails.evaluate(
            "analyze competitor at https://acme.com/pricing in market", "t1"
        )
        assert result.passed
        assert not result.blocked

    async def test_no_url_passes(self):
        result = await self.guardrails.evaluate(
            "analyze competitor Acme Corp in market", "t1"
        )
        assert result.passed

    async def test_multiple_urls_one_bad(self):
        result = await self.guardrails.evaluate(
            "compare https://acme.com and http://192.168.0.1/internal in market",
            "t1",
        )
        assert result.blocked
        assert result.rule_id == "IG-08"


class TestSSRFHelpers:
    def test_extract_urls(self):
        text = "visit https://a.com and http://b.com/path for details"
        urls = _extract_urls(text)
        assert len(urls) == 2

    def test_is_ssrf_localhost(self):
        assert _is_ssrf_target("http://localhost:8080/")

    def test_is_ssrf_private_ip(self):
        assert _is_ssrf_target("http://10.0.0.1/")
        assert _is_ssrf_target("http://172.16.0.1/")
        assert _is_ssrf_target("http://192.168.1.1/")
        assert _is_ssrf_target("http://127.0.0.1/")

    def test_is_ssrf_metadata(self):
        assert _is_ssrf_target("http://169.254.169.254/latest/")
        assert _is_ssrf_target("http://metadata.google.internal/v1/")

    def test_public_url_not_ssrf(self):
        assert not _is_ssrf_target("https://google.com/")
        assert not _is_ssrf_target("https://acme.com/pricing")

    def test_malformed_url(self):
        assert not _is_ssrf_target("not-a-url")
