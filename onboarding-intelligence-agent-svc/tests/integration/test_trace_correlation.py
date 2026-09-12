"""AC-3 — traces correlate across the service boundary.

Django sends a W3C ``traceparent``. The service must continue that trace
rather than starting its own, and every event it emits must carry the same
``trace_id``.

Verified against a real OpenTelemetry SDK with an in-memory exporter — real
spans, real propagation, real exported data. The half A-03 cannot verify is
the Django end: nothing in the monorepo emits traces yet (OIA is the only
service with `opentelemetry` in requirements), so "the same trace tree as the
Django span" is asserted here by feeding the service a genuine traceparent and
proving the trace id survives into the span and the event.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core.telemetry import (
    TraceContextMiddleware,
    current_trace_id,
    outbound_headers,
)
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.messaging.producer import KafkaProducer

pytestmark = [pytest.mark.integration]

# A valid W3C traceparent: version-traceid-spanid-flags.
UPSTREAM_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
UPSTREAM_SPAN_ID = "b7ad6b7169203331"
TRACEPARENT = f"00-{UPSTREAM_TRACE_ID}-{UPSTREAM_SPAN_ID}-01"


@pytest.fixture(scope="module")
def _memory_exporter() -> InMemorySpanExporter:
    """Attach an in-memory exporter to the process-wide tracer provider.

    OpenTelemetry permits the global provider to be set exactly once per
    process, and importing app.main sets it. Adding a processor to whichever
    provider is already installed works regardless of import order; replacing
    it would be silently ignored and every assertion would read an empty
    exporter.
    """
    memory = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return memory


@pytest.fixture
def exporter(_memory_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    """Each test reads only the spans it produced."""
    _memory_exporter.clear()
    return _memory_exporter


async def test_inbound_traceparent_is_continued(exporter):
    """The span the service opens belongs to the caller's trace."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(TraceContextMiddleware)

    @app.get("/probe")
    async def probe() -> dict:
        return {"trace_id": current_trace_id()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/probe", headers={"traceparent": TRACEPARENT})

    assert response.json()["trace_id"] == UPSTREAM_TRACE_ID
    assert response.headers["X-Trace-Id"] == UPSTREAM_TRACE_ID

    spans = exporter.get_finished_spans()
    assert spans, "no span was exported"
    assert format(spans[0].context.trace_id, "032x") == UPSTREAM_TRACE_ID
    # The server span is a child of the caller's span, not a new root.
    assert spans[0].parent is not None
    assert format(spans[0].parent.span_id, "016x") == UPSTREAM_SPAN_ID


async def test_a_request_without_a_traceparent_starts_its_own_trace(exporter):
    """No inbound context is not an error — it is a new trace."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(TraceContextMiddleware)

    @app.get("/probe")
    async def probe() -> dict:
        return {"trace_id": current_trace_id()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/probe")

    trace_id = response.json()["trace_id"]
    assert trace_id != UPSTREAM_TRACE_ID
    assert trace_id != "0" * 32
    assert exporter.get_finished_spans()[0].parent is None


async def test_emitted_event_carries_the_inbound_trace_id(exporter):
    """AC-3's core claim: the event joins the caller's trace."""
    from fastapi import FastAPI

    captured: list = []

    app = FastAPI()
    app.add_middleware(TraceContextMiddleware)
    emitter = EventEmitter(KafkaProducer.__new__(KafkaProducer))

    @app.get("/probe")
    async def probe() -> dict:
        event = emitter.build(
            EventType.AGENT_INVOKED,
            tenant_id=uuid.uuid4(),
            correlation_id="corr-trace-1",
        )
        captured.append(event)
        return {"trace_id": event.trace_id}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/probe", headers={"traceparent": TRACEPARENT})

    assert response.json()["trace_id"] == UPSTREAM_TRACE_ID
    assert captured[0].trace_id == UPSTREAM_TRACE_ID
    # The span id is the service's own span, not the caller's.
    assert captured[0].span_id != UPSTREAM_SPAN_ID
    assert captured[0].span_id != "0" * 16


async def test_outbound_headers_propagate_the_trace_downstream(exporter):
    """A call the service makes must carry the trace on to Django or POI."""
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("outbound"):
        headers = outbound_headers()
        trace_id = current_trace_id()

    assert "traceparent" in headers
    assert trace_id in headers["traceparent"]


async def test_live_session_span_uses_attributes_not_nesting(exporter):
    """A-03: a 45-minute span cannot nest a child per audio frame."""
    from app.core.telemetry import LiveSessionSpan

    with LiveSessionSpan("sess-1", "tenant-1") as session:
        for _ in range(50):
            session.record_frame()
        with session.batch():
            pass

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "oia.live_session" in spans
    assert "oia.analysis_batch" in spans

    session_span = spans["oia.live_session"]
    assert session_span.attributes["oia.frames_total"] == 50
    assert session_span.attributes["oia.batches_total"] == 1
    assert session_span.attributes["oia.session_id"] == "sess-1"

    # 50 frames produced one batch child, not 50 children.
    batch = spans["oia.analysis_batch"]
    assert batch.parent is not None
    assert batch.parent.span_id == session_span.context.span_id
