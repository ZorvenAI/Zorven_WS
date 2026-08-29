"""Unit tests for the prompt resolution chain (L-01).

Covers: fallback prompts, mapping, POI client, and PromptLoader.
All tests are unit-level — no Redis or network required.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.prompts.fallbacks import get_fallback_prompts, get_fallback_versions
from app.prompts.mapping import (
    ALL_PROMPT_IDS,
    LIVE_PROMPTS,
    PREP_PROMPTS,
    PROCESS_PROMPTS,
    PROMPT_MAP,
    poi_name,
)

pytestmark = pytest.mark.unit


class TestFallbackPrompts:
    def test_returns_all_nine_ids(self):
        prompts = get_fallback_prompts()
        assert len(prompts) == 9
        assert set(prompts.keys()) == set(ALL_PROMPT_IDS)

    def test_fallback_version_is_identifiable(self):
        versions = get_fallback_versions()
        for pid, version in versions.items():
            assert version == "fallback-v1", f"{pid} has unexpected version"

    def test_fallback_versions_cover_all_ids(self):
        versions = get_fallback_versions()
        assert set(versions.keys()) == set(ALL_PROMPT_IDS)

    def test_returns_a_copy(self):
        a = get_fallback_prompts()
        b = get_fallback_prompts()
        a["oia.research_brief"] = "MUTATED"
        assert b["oia.research_brief"] != "MUTATED"

    def test_every_template_is_nonempty(self):
        prompts = get_fallback_prompts()
        for pid, template in prompts.items():
            assert template.strip(), f"{pid} has empty template"


class TestPromptMapping:
    def test_all_nine_ids(self):
        assert len(ALL_PROMPT_IDS) == 9

    def test_mode_sets_are_disjoint(self):
        assert PREP_PROMPTS & LIVE_PROMPTS == frozenset()
        assert PREP_PROMPTS & PROCESS_PROMPTS == frozenset()
        assert LIVE_PROMPTS & PROCESS_PROMPTS == frozenset()

    def test_union_covers_all(self):
        union = PREP_PROMPTS | LIVE_PROMPTS | PROCESS_PROMPTS
        assert union == frozenset(ALL_PROMPT_IDS)

    def test_mapping_is_bijective(self):
        poi_names = list(PROMPT_MAP.values())
        assert len(poi_names) == len(set(poi_names))

    def test_poi_name_returns_correct_value(self):
        assert poi_name("oia.research_brief") == "zorven-oia-research-brief"
        assert poi_name("oia.media_analysis_multi") == "zorven-oia-media-analysis-multi"

    def test_poi_name_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown prompt_id"):
            poi_name("oia.nonexistent")

    def test_every_id_has_fallback_and_poi_name(self):
        prompts = get_fallback_prompts()
        for pid in ALL_PROMPT_IDS:
            assert pid in prompts, f"missing fallback for {pid}"
            assert poi_name(pid), f"missing poi_name for {pid}"

    def test_prep_has_two(self):
        assert len(PREP_PROMPTS) == 2

    def test_live_has_five(self):
        assert len(LIVE_PROMPTS) == 5

    def test_process_has_two(self):
        assert len(PROCESS_PROMPTS) == 2


class TestPOIClient:
    @pytest.mark.asyncio
    async def test_empty_url_returns_none(self):
        from app.services.poi_client import POIClient

        client = POIClient("")
        result = await client.get_production("zorven-oia-research-brief")
        assert result is None

    def test_configured_is_false_for_empty_url(self):
        from app.services.poi_client import POIClient

        client = POIClient("")
        assert not client.configured

    def test_configured_is_true_for_non_empty_url(self):
        from app.services.poi_client import POIClient

        client = POIClient("http://localhost:8110")
        assert client.configured

    @pytest.mark.asyncio
    async def test_connection_refused_returns_none(self):
        from app.services.poi_client import POIClient

        client = POIClient("http://localhost:19999", timeout=1.0)
        result = await client.get_production("zorven-oia-test", tenant_id="t-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_sends_tenant_header(self):
        from app.services.poi_client import POIClient

        received_headers: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_headers.update(dict(self.headers))
                body = json.dumps({"template": "hello", "version": "v1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", timeout=2.0)
        result = await client.get_production("zorven-oia-test", tenant_id="tenant-42")
        t.join(timeout=3)
        server.server_close()

        assert result is not None
        assert result == ("hello", "v1")
        lower_headers = {k.lower(): v for k, v in received_headers.items()}
        assert lower_headers.get("x-tenant-id") == "tenant-42"

    @pytest.mark.asyncio
    async def test_handles_404(self):
        from app.services.poi_client import POIClient

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", timeout=2.0)
        result = await client.get_production("nonexistent")
        t.join(timeout=3)
        server.server_close()

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_500(self):
        from app.services.poi_client import POIClient

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(500)
                self.end_headers()

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", timeout=2.0)
        result = await client.get_production("zorven-oia-test")
        t.join(timeout=3)
        server.server_close()

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        from app.services.poi_client import POIClient

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                import time

                time.sleep(5)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", timeout=0.3)
        result = await client.get_production("zorven-oia-test")
        server.server_close()

        assert result is None

    @pytest.mark.asyncio
    async def test_no_tenant_header_when_none(self):
        from app.services.poi_client import POIClient

        received_headers: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_headers.update(dict(self.headers))
                body = json.dumps({"template": "t", "version": "v1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", timeout=2.0)
        await client.get_production("zorven-oia-test")
        t.join(timeout=3)
        server.server_close()

        lower_headers = {k.lower(): v for k, v in received_headers.items()}
        assert "x-tenant-id" not in lower_headers

    @pytest.mark.asyncio
    async def test_breaker_records_failure_on_timeout(self):
        from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
        from app.services.poi_client import POIClient

        config = BreakerConfig(
            name="test-poi",
            failure_threshold=3,
            window_seconds=60,
            success_threshold=2,
            half_open_max_calls=1,
            reset_timeout_seconds=60,
            degraded_mode="skip",
            user_message=None,
        )
        breaker = CircuitBreaker(config=config)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                import time

                time.sleep(5)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        client = POIClient(f"http://127.0.0.1:{port}", breaker=breaker, timeout=0.3)
        await client.get_production("zorven-oia-test")
        server.server_close()

        assert len(breaker._failures) >= 1


class TestFetchPromptsSkill:
    @pytest.mark.asyncio
    async def test_no_loader_returns_degraded(self):
        from app.skills.fetch_prompts import FetchPrompts
        from app.skills.models import SkillContext, TenantContext

        skill = FetchPrompts(meta=None, prompt_loader=None)
        ctx = SkillContext(
            input_prompt="",
            tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
            input_context={"mode": "PREP"},
        )
        result = await skill.run(ctx)
        assert result.output["degraded"] is True
        assert result.output["prompt_versions"] == {}
        assert result.skill_id == "SKL-OIA-15"
