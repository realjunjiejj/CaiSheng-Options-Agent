"""Unit tests for configuration resolution, secret redaction, and submission kill switch."""

import os
from pathlib import Path
import subprocess
import sys
import pytest
from volagent.config import load_config
from volagent.logging import redact_secrets


def test_secret_redactor_handles_keys_lists_and_provider_formats():
    """Verify CS-16 & CS-18: Secret redactor masks API keys and nested secret dictionaries."""
    data = {
        "alpaca_secret_key": "secret_12345",
        "api_key": "PK1234567890123456",
        "nested": [
            {"user": "alice", "token": "sk-12345678901234567890"},
            ("sensitive_string", "AIzaSyD-1234567890123456789012345678901"),
        ],
    }

    redacted = redact_secrets(data)
    assert redacted["alpaca_secret_key"] == "***REDACTED***"
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"][0]["token"] == "***REDACTED***"
    assert "AIza" in redacted["nested"][1][1] and "***REDACTED***" in redacted["nested"][1][1]


def test_config_submission_kill_switch_defaults_to_false():
    """Verify EX-09 & Gate 0: Order submission is disabled by default."""
    cfg = load_config()
    assert cfg.execution.allow_order_submission is False
    assert cfg.volagent_allow_order_submission is False


def test_documented_environment_variables_load(monkeypatch):
    """P1-10 Fix: Documented environment variables load properly."""
    monkeypatch.setenv("DATA_MODE", "replay_real")
    monkeypatch.setenv("ALPACA_API_KEY", "test-api-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret-key")

    cfg = load_config()
    assert cfg.volagent_data_mode == "replay_real"
    assert cfg.alpaca_api_key == "test-api-key"
    assert cfg.alpaca_secret_key == "test-secret-key"


def test_all_ui_modules_import():
    """P1-34 & P2-07 Fix: Verify all UI modules and pages import without error."""
    import volagent.ui.charts
    import volagent.ui.theme
    import volagent.ui.pages.analyze
    import volagent.ui.pages.audit
    import volagent.ui.pages.decision
    import volagent.ui.pages.scoreboard
    assert volagent.ui.charts is not None
    assert volagent.ui.pages.decision is not None


def test_symbol_must_match_scenario_underlying():
    """P1-17 Fix: Enforce that --symbol and --scenario underlying match."""
    env = {**os.environ, "PYTHONPATH": "src"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "ValidationError" in proc.stdout or "ValidationError" in proc.stderr
