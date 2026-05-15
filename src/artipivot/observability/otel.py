"""OpenTelemetry integration — optional metrics/traces export."""

from __future__ import annotations

import os
from contextlib import suppress

_OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false") == "true"

# Module-level meter — None when OTel is disabled
_meter = None
_tracer = None

# Metric instruments (created lazily)
_request_duration = None
_classify_duration = None
_tool_duration = None
_tool_errors = None
_intent_distribution = None
_circuit_opens = None


def setup_otel(app=None) -> None:
    """Initialize OTel — only when OTEL_ENABLED=true."""
    global _meter, _tracer
    global _request_duration, _classify_duration, _tool_duration
    global _tool_errors, _intent_distribution, _circuit_opens

    if not _OTEL_ENABLED:
        return

    with suppress(ImportError):
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.trace import TracerProvider

        # FastAPI auto-instrumentation
        if app is not None:
            with suppress(ImportError):
                from opentelemetry.instrumentation.fastapi import (
                    FastAPIInstrumentor,
                )

                FastAPIInstrumentor.instrument_app(app)

        _meter = metrics.get_meter("artipivot")
        _tracer = trace.get_tracer("artipivot")

        # Core metrics
        _request_duration = _meter.create_histogram(
            "artipivot.request.duration", unit="ms"
        )
        _classify_duration = _meter.create_histogram(
            "artipivot.classify.duration", unit="ms"
        )
        _tool_duration = _meter.create_histogram(
            "artipivot.tool.duration", unit="ms"
        )
        _tool_errors = _meter.create_counter("artipivot.tool.errors")
        _intent_distribution = _meter.create_counter(
            "artipivot.intent.classified"
        )
        _circuit_opens = _meter.create_counter("artipivot.circuit.opens")


def is_enabled() -> bool:
    """Check if OTel is enabled."""
    return _OTEL_ENABLED


def record_request_duration(duration_ms: float, **attrs) -> None:
    if _request_duration:
        _request_duration.record(duration_ms, attrs)


def record_classify_duration(duration_ms: float, **attrs) -> None:
    if _classify_duration:
        _classify_duration.record(duration_ms, attrs)


def record_tool_duration(duration_ms: float, **attrs) -> None:
    if _tool_duration:
        _tool_duration.record(duration_ms, attrs)


def record_tool_error(**attrs) -> None:
    if _tool_errors:
        _tool_errors.add(1, attrs)


def record_intent(intent: str, **attrs) -> None:
    if _intent_distribution:
        _intent_distribution.add(1, {"intent": intent, **attrs})


def record_circuit_open(circuit: str, **attrs) -> None:
    if _circuit_opens:
        _circuit_opens.add(1, {"circuit": circuit, **attrs})
