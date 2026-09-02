"""Security and behavior tests for the judge-facing Alpaca Lockbox."""

from __future__ import annotations

import asyncio
import json
import subprocess

from volagent.config import PROJECT_ROOT, VolAgentSettings
from volagent.integrations.alpaca_lockbox import (
    OFFICIAL_MCP_TOOLSETS,
    PAPER_TRADING_ENDPOINT,
    _is_read_only_tool_name,
    run_alpaca_technology_lockbox,
    verify_official_alpaca_cli,
    verify_official_alpaca_mcp,
    verify_official_alpaca_skills,
)


def _completed(command: list[str], stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def _settings() -> VolAgentSettings:
    settings = VolAgentSettings()
    settings.alpaca_api_key = "LOCKBOX-TEST-KEY"
    settings.alpaca_secret_key = "LOCKBOX-TEST-SECRET"
    settings.alpaca_paper_trade = True
    return settings


def test_official_cli_proves_exact_paper_endpoint_and_sanitizes_secrets():
    calls: list[tuple[list[str], dict[str, str]]] = []

    def runner(command, *, env, timeout):
        calls.append((list(command), env))
        if command[-1] == "version":
            return _completed(command, "0.0.14\n")
        if command[-1] == "doctor":
            return _completed(command, f"Trading:  {PAPER_TRADING_ENDPOINT}\nAll checks passed.\n")
        if command[1:3] == ["account", "get"]:
            return _completed(
                command,
                json.dumps(
                    {
                        "id": "DO-NOT-RENDER",
                        "account_number": "DO-NOT-RENDER-EITHER",
                        "status": "ACTIVE",
                        "equity": "100000",
                        "buying_power": "200000",
                        "options_approved_level": 3,
                        "options_trading_level": 3,
                    }
                ),
            )
        return _completed(
            command,
            json.dumps(
                {
                    "clocks": [
                        {
                            "market": {"mic": "XNYS"},
                            "phase": "closed",
                            "is_market_day": False,
                            "next_market_open": "2026-08-31T09:30:00-04:00",
                            "next_market_close": "2026-08-31T16:00:00-04:00",
                            "timestamp": "2026-08-30T01:00:00-04:00",
                        }
                    ]
                }
            ),
        )

    receipt = verify_official_alpaca_cli(
        _settings(), runner=runner, executable="/test/alpaca"
    )

    assert receipt["status"] == "PASS"
    assert receipt["paper_endpoint_verified"] is True
    assert receipt["account"]["equity"] == 100000.0
    rendered = json.dumps(receipt)
    assert "LOCKBOX-TEST-KEY" not in rendered
    assert "LOCKBOX-TEST-SECRET" not in rendered
    assert "DO-NOT-RENDER" not in rendered
    assert all("LOCKBOX-TEST" not in " ".join(command) for command, _ in calls)
    assert all(env["ALPACA_LIVE_TRADE"] == "false" for _, env in calls)
    assert all("ALPACA_PROFILE" not in env for _, env in calls)


def test_official_cli_fails_closed_if_doctor_resolves_live_endpoint():
    def runner(command, *, env, timeout):
        if command[-1] == "version":
            return _completed(command, "0.0.14\n")
        if command[-1] == "doctor":
            return _completed(command, "Trading:  https://api.alpaca.markets\n")
        return _completed(command, "{}")

    receipt = verify_official_alpaca_cli(
        _settings(), runner=runner, executable="/test/alpaca"
    )

    assert receipt["status"] == "FAIL"
    assert receipt["paper_endpoint_verified"] is False


def test_official_cli_fails_closed_for_inactive_account():
    def runner(command, *, env, timeout):
        if command[-1] == "version":
            return _completed(command, "0.0.14\n")
        if command[-1] == "doctor":
            return _completed(command, f"Trading:  {PAPER_TRADING_ENDPOINT}\n")
        if command[1:3] == ["account", "get"]:
            return _completed(
                command,
                json.dumps(
                    {
                        "status": "ACCOUNT_UPDATED",
                        "equity": "100000",
                        "buying_power": "200000",
                    }
                ),
            )
        return _completed(
            command,
            json.dumps(
                {
                    "clocks": [
                        {
                            "market": {"mic": "XNYS"},
                            "phase": "closed",
                            "timestamp": "2026-08-30T01:00:00-04:00",
                        }
                    ]
                }
            ),
        )

    receipt = verify_official_alpaca_cli(
        _settings(), runner=runner, executable="/test/alpaca"
    )

    assert receipt["status"] == "FAIL"
    assert "ValueError" in receipt["reason"]


def test_mcp_lockbox_toolsets_exclude_trading_and_account_mutations():
    assert OFFICIAL_MCP_TOOLSETS == ("assets", "options-data")
    for unsafe in (
        "submit_order",
        "close_all_positions",
        "exercise_options_position",
        "update_account_config",
        "cancel_all_orders",
    ):
        assert _is_read_only_tool_name(unsafe) is False
    for safe in ("get_clock", "get_option_chain", "search_alpaca_docs"):
        assert _is_read_only_tool_name(safe) is True


def test_mcp_wrapper_returns_only_injected_sanitized_proof():
    async def probe(_settings):
        await asyncio.sleep(0)
        return {
            "component": "official_alpaca_mcp_v2",
            "status": "PASS",
            "paper_mode_configured": True,
            "configured_toolsets": ["assets", "options-data"],
            "trading_toolset_excluded": True,
        }

    receipt = verify_official_alpaca_mcp(_settings(), probe=probe)

    assert receipt["status"] == "PASS"
    assert receipt["paper_mode_configured"] is True
    assert "LOCKBOX-TEST" not in json.dumps(receipt)


def test_official_alpaca_skills_are_installed_and_fingerprinted():
    receipt = verify_official_alpaca_skills(project_root=PROJECT_ROOT)

    assert receipt["status"] == "PASS"
    assert len(receipt["verified"]) == 4
    assert all(len(skill["sha256"]) == 64 for skill in receipt["verified"])
    assert all(len(skill["reference_sha256"]) == 64 for skill in receipt["verified"])


def test_combined_lockbox_requires_every_component_to_pass():
    def cli(_settings):
        return {"component": "cli", "status": "PASS"}

    def mcp(_settings):
        return {"component": "mcp", "status": "FAIL"}

    def skills():
        return {"component": "skills", "status": "PASS"}

    receipt = run_alpaca_technology_lockbox(
        _settings(), cli_verifier=cli, mcp_verifier=mcp, skills_verifier=skills
    )

    assert receipt["overall_status"] == "FAIL"
    assert receipt["paper_only"] is True
    assert "canonical approval" in receipt["execution_boundary"]


def test_cockpit_exposes_integration_checks_without_claiming_an_alpaca_product():
    source = (PROJECT_ROOT / "src/volagent/ui/pages/cockpit.py").read_text()

    assert "Run Alpaca integration checks" in source
    assert "not an Alpaca product" in source
    assert "paper-only order boundary" in source
    assert "run_alpaca_technology_lockbox" in source


def test_cli_exposes_lockbox_command():
    source = (PROJECT_ROOT / "cli.py").read_text()

    assert '"--lockbox"' in source
    assert "run_alpaca_technology_lockbox" in source


def test_only_canonical_gateway_may_submit_alpaca_orders():
    """No UI, agent, MCP, or lifecycle module may bypass the gateway."""
    source_root = PROJECT_ROOT / "src/volagent"
    gateway = source_root / "execution/alpaca.py"
    offenders = []
    for path in source_root.rglob("*.py"):
        if path == gateway:
            continue
        if ".submit_order(" in path.read_text():
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], f"Direct Alpaca submission outside gateway: {offenders}"
