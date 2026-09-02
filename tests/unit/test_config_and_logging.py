"""Unit tests for configuration resolution, secret redaction, and submission kill switch."""

import os
from pathlib import Path
import subprocess
import sys
import pytest
import volagent.config as config_module
from volagent.config import load_config
from volagent.errors import ConfigurationError
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


def test_persistent_dotenv_cannot_enable_order_submission(monkeypatch):
    """A stale local file must not silently re-arm the paper-order write path."""
    import volagent.config as config_module

    monkeypatch.delenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", raising=False)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {"VOLAGENT_ALLOW_ORDER_SUBMISSION": "true"},
    )

    cfg = config_module.load_config()

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


def test_documented_alpaca_variables_load_from_project_dotenv(monkeypatch):
    """Unprefixed documented values in .env must reach the paper broker."""
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _: {
            "ALPACA_API_KEY": "dotenv-api-key",
            "ALPACA_SECRET_KEY": "dotenv-secret-key",
            "ALPACA_PAPER_TRADE": "true",
            "VOLAGENT_ALLOW_ORDER_SUBMISSION": "false",
        },
    )

    cfg = load_config()

    assert cfg.alpaca_api_key == "dotenv-api-key"
    assert cfg.alpaca_secret_key == "dotenv-secret-key"
    assert cfg.alpaca_paper_trade is True
    assert cfg.execution.allow_order_submission is False


def test_process_environment_overrides_project_dotenv(monkeypatch):
    """Deployment-injected credentials take precedence over a local .env file."""
    monkeypatch.setenv("ALPACA_API_KEY", "process-api-key")
    monkeypatch.setattr(config_module, "dotenv_values", lambda _: {"ALPACA_API_KEY": "dotenv-api-key"})

    assert load_config().alpaca_api_key == "process-api-key"


def test_autonomous_approval_policy_can_be_explicitly_overridden(monkeypatch):
    """Persistent runner can opt out of human approval only via an explicit flag."""
    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "false")
    assert load_config().execution.require_human_approval is False

    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "true")
    assert load_config().execution.require_human_approval is True


def test_live_trading_configuration_is_rejected_from_project_dotenv(monkeypatch):
    """A .env file can never opt the application into live trading."""
    monkeypatch.setattr(config_module, "dotenv_values", lambda _: {"ALPACA_PAPER_TRADE": "false"})

    with pytest.raises(ConfigurationError, match="ALPACA_PAPER_TRADE must be True"):
        load_config()


def test_all_ui_modules_import():
    """P1-34 & P2-07 Fix: Verify all UI modules and pages import without error."""
    import volagent.ui.charts
    import volagent.ui.theme
    import volagent.ui.pages.analyze
    import volagent.ui.pages.audit
    import volagent.ui.pages.decision
    import volagent.ui.pages.research
    import volagent.ui.pages.rough_vol_simulator
    import volagent.ui.pages.scoreboard
    assert volagent.ui.charts is not None
    assert volagent.ui.pages.decision is not None
    assert volagent.ui.pages.research is not None
    assert volagent.ui.pages.rough_vol_simulator is not None


def test_symbol_must_match_scenario_underlying():
    """P1-17 Fix: Enforce that --symbol and --scenario underlying match."""
    env = {**os.environ, "PYTHONPATH": "src"}
    cmd = [sys.executable, "cli.py", "--symbol", "AAPL", "--scenario", "SCENARIO-NVDA-2024Q2-AMC", "--output-json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "ValidationError" in proc.stdout or "ValidationError" in proc.stderr
