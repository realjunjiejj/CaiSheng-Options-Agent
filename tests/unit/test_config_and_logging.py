"""Unit tests for configuration resolution, secret redaction, and submission kill switch."""

import os
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
