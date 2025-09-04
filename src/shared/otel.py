from __future__ import annotations

import os
from typing import Any
from contextlib import contextmanager


def init_tracing(app: Any) -> bool:
    """Initialize OpenTelemetry tracing if enabled and available.

    Returns True if tracing initialized, else False. Safe no-op when OTEL
    packages are not installed or ENABLE_OTEL is not set.
    """
    if os.getenv("ENABLE_OTEL", "false").lower() != "true":
        return False
    try:
        # Core SDK + OTLP exporter
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # Instrumentations (optional)
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
        except Exception:
            pass
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument()
        except Exception:
            pass

        service_name = os.getenv("OTEL_SERVICE_NAME", "vedacore-api")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
            headers={},
        )
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(provider)
        return True
    except Exception:
        # Missing deps or exporter; run without tracing
        return False


# ---------- Lightweight tracer helper (safe if OTEL not installed) ---------

class _NoopSpan:
    def set_attribute(self, *_: Any, **__: Any) -> None:
        return None

@contextmanager
def _noop_cm():
    yield _NoopSpan()


class _NoopTracer:
    def start_as_current_span(self, *_: Any, **__: Any):  # type: ignore
        return _noop_cm()


def get_tracer(service: str = "vedacore-api"):
    """Return an OTEL tracer or a no-op tracer if OTEL not installed.

    Usage:
      tracer = get_tracer("stream")
      with tracer.start_as_current_span("stream.publish") as span:
          span.set_attribute("topic", topic)
    """
    try:
        from opentelemetry import trace  # type: ignore
        return trace.get_tracer(service)
    except Exception:
        return _NoopTracer()
