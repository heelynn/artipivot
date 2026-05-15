"""Tests for P5 OpenTelemetry integration."""

from __future__ import annotations

import os

import pytest


class TestOTelDisabled:
    def test_setup_no_error_when_disabled(self):
        from artipivot.observability.otel import setup_otel

        os.environ["OTEL_ENABLED"] = "false"
        setup_otel()  # Should not raise or import OTel

    def test_is_enabled_false(self):
        from artipivot.observability.otel import is_enabled

        os.environ["OTEL_ENABLED"] = "false"
        assert is_enabled() is False

    def test_record_functions_noop(self):
        from artipivot.observability.otel import (
            record_circuit_open,
            record_classify_duration,
            record_intent,
            record_request_duration,
            record_tool_duration,
            record_tool_error,
        )

        # All should silently skip
        record_request_duration(100.0)
        record_classify_duration(50.0)
        record_tool_duration(30.0)
        record_tool_error()
        record_intent("code_write")
        record_circuit_open("provider_a")


class TestOTelEnabled:
    def test_is_enabled_true(self):
        os.environ["OTEL_ENABLED"] = "true"
        # Re-import to pick up env change
        import importlib

        import artipivot.observability.otel as otel_mod

        importlib.reload(otel_mod)
        assert otel_mod.is_enabled() is True

        # Cleanup
        os.environ["OTEL_ENABLED"] = "false"
        importlib.reload(otel_mod)
