"""OpenTelemetry setup, W3C propagation and the live-session span convention.

Providers are installed unconditionally so instrumentation can be written
without null checks, but nothing is exported unless
``OIA_OTEL_EXPORTER_ENDPOINT`` is set — local runs and CI stay free of
connection noise with one environment variable between here and a collector.

**Trace correlation (AC-3).** Django sends a W3C ``traceparent`` header.
:class:`TraceContextMiddleware` extracts it and makes the resulting context
current for the request, so a span opened here — and any event emitted, since
:class:`~app.events.emitter.EventEmitter` reads ``trace_id`` from the active
span — lands in the caller's trace rather than starting a new one.

**Live sessions (A-03 technical note).** One span covers a whole meeting and
child spans cover each analysis batch. A 45-minute span cannot accumulate
nested children per audio frame without becoming unreadable, so per-frame
detail is recorded with ``set_attribute`` and span events on the session span
instead. :class:`LiveSessionSpan` encodes that convention.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Awaitable, Callable

from opentelemetry import metrics, trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SERVICE = "onboarding-intelligence-agent"

TRACEPARENT_HEADER = "traceparent"


def configure_telemetry(exporter_endpoint: str = "") -> None:
    """Install tracer and meter providers.

    With no endpoint the providers are installed but no exporter is attached,
    so spans are created and dropped rather than buffered or retried.
    """
    resource = Resource.create({SERVICE_NAME: _SERVICE})

    tracer_provider = TracerProvider(resource=resource)
    if exporter_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=exporter_endpoint))
        )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(MeterProvider(resource=resource))


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)


def get_meter() -> metrics.Meter:
    return metrics.get_meter(_SERVICE)


def current_trace_id() -> str:
    """Hex trace id of the active span, or 32 zeros when there is none."""
    return format(trace.get_current_span().get_span_context().trace_id, "032x")


def current_span_id() -> str:
    return format(trace.get_current_span().get_span_context().span_id, "016x")


def outbound_headers() -> dict[str, str]:
    """Headers that propagate the current trace to a downstream call."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Continues an inbound W3C trace and opens a server span for the request.

    Without this the service would start a fresh trace per request and the
    Django span and the OIA span would sit in two unrelated trees — which is
    precisely the failure AC-3 is written to prevent.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        context = extract(dict(request.headers))
        tracer = get_tracer()
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=context,
            kind=trace.SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            # Handy for correlating a user-reported request with a trace.
            response.headers["X-Trace-Id"] = current_trace_id()
            return response


class LiveSessionSpan:
    """One span for a whole live meeting, per the A-03 technical note.

    Batches get child spans via :meth:`batch`; per-frame facts are folded into
    counters on the session span with :meth:`record_frame` rather than becoming
    thousands of children.
    """

    def __init__(self, session_id: str, tenant_id: str) -> None:
        self._tracer = get_tracer()
        self._span: Span | None = None
        self._session_id = session_id
        self._tenant_id = tenant_id
        self._frames = 0
        self._batches = 0

    def __enter__(self) -> "LiveSessionSpan":
        self._span = self._tracer.start_span("oia.live_session")
        self._span.set_attribute("oia.session_id", self._session_id)
        self._span.set_attribute("oia.tenant_id", self._tenant_id)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._span is None:
            return
        self._span.set_attribute("oia.frames_total", self._frames)
        self._span.set_attribute("oia.batches_total", self._batches)
        if exc is not None:
            self._span.set_status(Status(StatusCode.ERROR, str(exc)))
        self._span.end()
        self._span = None

    def record_frame(self, **attributes: Any) -> None:
        """Fold one frame into the session span without nesting a child."""
        self._frames += 1
        if self._span is not None and attributes:
            for key, value in attributes.items():
                self._span.set_attribute(f"oia.{key}", value)

    def batch(self, name: str = "oia.analysis_batch") -> Any:
        """A child span for one analysis batch."""
        self._batches += 1
        context = trace.set_span_in_context(self._span) if self._span else None
        return self._tracer.start_as_current_span(name, context=context)
