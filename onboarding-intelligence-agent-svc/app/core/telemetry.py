"""OpenTelemetry tracer and meter setup.

Initialised unconditionally so instrumentation code can be written without
null-checks, but it exports nothing unless ``OIA_OTEL_EXPORTER_ENDPOINT`` is
set. That keeps local runs and CI free of connection noise while leaving a
single environment variable between here and a real backend.

Dashboards and the alert catalogue are Design §20 and are not in A-05's scope.
"""

from __future__ import annotations

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_SERVICE = "onboarding-intelligence-agent"


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
