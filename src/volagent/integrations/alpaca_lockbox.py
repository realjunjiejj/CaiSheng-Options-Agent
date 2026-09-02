"""Fail-closed proof bundle for Alpaca's official CLI, MCP server, and skills.

The "Lockbox" is a CaiSheng presentation pattern, not an Alpaca product.  It
proves that the application can use Alpaca's official agent interfaces without
creating another order path.  The official MCP subprocess is intentionally
limited to read-only market-data toolsets; CaiSheng's guarded broker gateway
remains the sole component allowed to submit paper orders.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from volagent.config import PROJECT_ROOT, VolAgentSettings, load_config


PAPER_TRADING_ENDPOINT = "https://paper-api.alpaca.markets"
OFFICIAL_MCP_TOOLSETS = ("assets", "options-data")
REQUIRED_ALPACA_SKILLS = {
    "backtest": "alpaca-trading-backtest",
    "paper-trading": "alpaca-trading-paper-trading",
    "paper-trading-cli": "alpaca-trading-paper-trading-cli",
    "paper-trading-mcp": "alpaca-trading-paper-trading-mcp",
}
_MUTATING_TOOL_TOKENS = {
    "submit",
    "create",
    "update",
    "delete",
    "cancel",
    "replace",
    "close",
    "exercise",
    "order",
    "position",
    "watchlist",
    "locate",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _failure(component: str, reason: str, **facts: Any) -> dict[str, Any]:
    return {
        "component": component,
        "status": "FAIL",
        "verified_at": _utc_now(),
        "reason": reason,
        **facts,
    }


def _credentials_present(settings: VolAgentSettings) -> bool:
    return bool(settings.alpaca_api_key and settings.alpaca_secret_key)


def _paper_cli_environment(settings: VolAgentSettings) -> dict[str, str]:
    """Build an explicit paper-only environment without returning it in receipts."""
    if not _credentials_present(settings):
        raise ValueError("Alpaca credentials are not configured.")
    env = os.environ.copy()
    env.update(
        {
            "ALPACA_API_KEY": str(settings.alpaca_api_key),
            "ALPACA_SECRET_KEY": str(settings.alpaca_secret_key),
            "ALPACA_LIVE_TRADE": "false",
            "ALPACA_QUIET": "1",
        }
    )
    # An unrelated active profile must never override the explicit paper bundle.
    env.pop("ALPACA_PROFILE", None)
    return env


def _run_command(
    command: Sequence[str],
    *,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _parse_json_result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if process.returncode != 0:
        raise RuntimeError(f"command exited with status {process.returncode}")
    parsed = json.loads(process.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _safe_equity(value: Any) -> float:
    number = float(value)
    if not (number > 0 and number < float("inf")):
        raise ValueError("equity must be positive and finite")
    return number


def _safe_nonnegative_number(value: Any, field_name: str) -> float:
    number = float(value)
    if not (number >= 0 and number < float("inf")):
        raise ValueError(f"{field_name} must be nonnegative and finite")
    return number


def verify_official_alpaca_cli(
    settings: VolAgentSettings | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run_command,
    executable: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Verify the official agent-first CLI using read-only paper API calls.

    The returned receipt deliberately excludes account identifiers, credentials,
    raw stdout/stderr, and profile paths.
    """
    settings = settings or load_config()
    binary = executable or shutil.which("alpaca")
    if not binary:
        return _failure("official_alpaca_cli", "Official Alpaca CLI is not installed.")
    if not settings.alpaca_paper_trade:
        return _failure("official_alpaca_cli", "CaiSheng is not configured for paper trading.")
    if not _credentials_present(settings):
        return _failure("official_alpaca_cli", "Alpaca paper credentials are missing.")

    try:
        env = _paper_cli_environment(settings)
        version_result = runner([binary, "version"], env=env, timeout=timeout)
        doctor_result = runner([binary, "doctor"], env=env, timeout=timeout)
        account_result = runner(
            [binary, "account", "get", "--quiet"], env=env, timeout=timeout
        )
        clock_result = runner(
            [binary, "clock", "markets", "--quiet"], env=env, timeout=timeout
        )
        if any(
            result.returncode != 0
            for result in (version_result, doctor_result, account_result, clock_result)
        ):
            return _failure(
                "official_alpaca_cli",
                "One or more official CLI read checks failed.",
                command_status={
                    "version": version_result.returncode,
                    "doctor": doctor_result.returncode,
                    "account_get": account_result.returncode,
                    "clock_markets": clock_result.returncode,
                },
            )

        doctor_text = doctor_result.stdout
        if PAPER_TRADING_ENDPOINT not in doctor_text:
            return _failure(
                "official_alpaca_cli",
                "CLI diagnostics did not resolve the exact Alpaca paper endpoint.",
                paper_endpoint_verified=False,
            )
        if "https://api.alpaca.markets" in doctor_text:
            return _failure(
                "official_alpaca_cli",
                "CLI diagnostics exposed a live trading endpoint.",
                paper_endpoint_verified=False,
            )

        account = _parse_json_result(account_result)
        if account.get("status") != "ACTIVE":
            raise ValueError("paper account is not active")
        clocks = _parse_json_result(clock_result).get("clocks") or []
        if not isinstance(clocks, list):
            raise ValueError("clock response did not contain a list")
        nyse_clock = next(
            (
                clock
                for clock in clocks
                if isinstance(clock, dict)
                and isinstance(clock.get("market"), dict)
                and clock["market"].get("mic") == "XNYS"
            ),
            None,
        )
        if nyse_clock is None:
            raise ValueError("NYSE clock was absent from official CLI response")

        return {
            "component": "official_alpaca_cli",
            "status": "PASS",
            "verified_at": _utc_now(),
            "version": version_result.stdout.strip(),
            "paper_endpoint_verified": True,
            "resolved_trading_endpoint": PAPER_TRADING_ENDPOINT,
            "read_checks": ["doctor", "account get", "clock markets"],
            "account": {
                "status": account.get("status"),
                "equity": _safe_equity(account.get("equity")),
                "buying_power": _safe_nonnegative_number(
                    account.get("buying_power"), "buying power"
                ),
                "options_approved_level": account.get("options_approved_level"),
                "options_trading_level": account.get("options_trading_level"),
            },
            "nyse_clock": {
                "phase": nyse_clock.get("phase"),
                "is_market_day": nyse_clock.get("is_market_day"),
                "next_open": nyse_clock.get("next_market_open"),
                "next_close": nyse_clock.get("next_market_close"),
                "timestamp": nyse_clock.get("timestamp"),
            },
        }
    except (OSError, subprocess.SubprocessError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return _failure(
            "official_alpaca_cli",
            f"Official CLI verification failed closed: {type(exc).__name__}.",
        )


def _is_read_only_tool_name(name: str) -> bool:
    tokens = set(name.lower().replace("-", "_").split("_"))
    return not bool(tokens & _MUTATING_TOOL_TOKENS)


async def _probe_official_mcp(
    settings: VolAgentSettings,
    *,
    command: str = "uvx",
    package: str = "alpaca-mcp-server",
    timeout: float = 30.0,
) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        "ALPACA_API_KEY": str(settings.alpaca_api_key),
        "ALPACA_SECRET_KEY": str(settings.alpaca_secret_key),
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_TOOLSETS": ",".join(OFFICIAL_MCP_TOOLSETS),
    }
    server = StdioServerParameters(command=command, args=[package], env=env)
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with asyncio.timeout(timeout):
            async with stdio_client(server, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    discovered = await session.list_tools()
                    tool_names = sorted(tool.name for tool in discovered.tools)
                    unsafe_tools = [name for name in tool_names if not _is_read_only_tool_name(name)]
                    if unsafe_tools:
                        return _failure(
                            "official_alpaca_mcp_v2",
                            "Restricted MCP discovery exposed a mutating tool.",
                            unsafe_tools=unsafe_tools,
                            paper_mode_configured=True,
                            configured_toolsets=list(OFFICIAL_MCP_TOOLSETS),
                        )
                    if "get_clock" not in tool_names:
                        return _failure(
                            "official_alpaca_mcp_v2",
                            "Dynamic discovery did not expose the read-only market clock.",
                            paper_mode_configured=True,
                            configured_toolsets=list(OFFICIAL_MCP_TOOLSETS),
                        )

                    clock_result = await session.call_tool("get_clock", {})
                    if getattr(clock_result, "isError", False):
                        return _failure(
                            "official_alpaca_mcp_v2",
                            "The dynamically discovered market-clock call failed.",
                            paper_mode_configured=True,
                            configured_toolsets=list(OFFICIAL_MCP_TOOLSETS),
                        )

                    clock_data: dict[str, Any] = {}
                    for content in getattr(clock_result, "content", []):
                        text = getattr(content, "text", None)
                        if not isinstance(text, str):
                            continue
                        try:
                            payload = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        candidate = payload.get("data") if isinstance(payload, dict) else None
                        if isinstance(candidate, dict):
                            clock_data = candidate
                            break
                    if not isinstance(clock_data.get("is_open"), bool) or not clock_data.get(
                        "timestamp"
                    ):
                        return _failure(
                            "official_alpaca_mcp_v2",
                            "The market-clock response was not parseable.",
                            paper_mode_configured=True,
                            configured_toolsets=list(OFFICIAL_MCP_TOOLSETS),
                        )

                    return {
                        "component": "official_alpaca_mcp_v2",
                        "status": "PASS",
                        "verified_at": _utc_now(),
                        "server": package,
                        "transport": "stdio",
                        "paper_mode_configured": True,
                        "configured_toolsets": list(OFFICIAL_MCP_TOOLSETS),
                        "trading_toolset_excluded": True,
                        "dynamic_discovery": True,
                        "discovered_tool_count": len(tool_names),
                        "discovered_tools": tool_names,
                        "read_call": "get_clock",
                        "market_clock": {
                            "is_open": clock_data.get("is_open"),
                            "next_open": clock_data.get("next_open"),
                            "next_close": clock_data.get("next_close"),
                            "timestamp": clock_data.get("timestamp"),
                        },
                    }


def verify_official_alpaca_mcp(
    settings: VolAgentSettings | None = None,
    *,
    probe: Callable[[VolAgentSettings], Any] | None = None,
) -> dict[str, Any]:
    """Discover and call the official MCP V2 server in a read-only sandbox."""
    settings = settings or load_config()
    if not settings.alpaca_paper_trade:
        return _failure("official_alpaca_mcp_v2", "CaiSheng is not in paper mode.")
    if not _credentials_present(settings):
        return _failure("official_alpaca_mcp_v2", "Alpaca paper credentials are missing.")
    if probe is None and not shutil.which("uvx"):
        return _failure("official_alpaca_mcp_v2", "uvx is required to launch Alpaca MCP V2.")

    try:
        return asyncio.run((probe or _probe_official_mcp)(settings))
    except Exception as exc:
        # MCP clients can wrap transport failures in an ExceptionGroup.  Never
        # render nested exception text because subprocess diagnostics may carry
        # implementation or environment details.
        return _failure(
            "official_alpaca_mcp_v2",
            f"Official MCP verification failed closed: {type(exc).__name__}.",
            paper_mode_configured=True,
            configured_toolsets=list(OFFICIAL_MCP_TOOLSETS),
        )


def verify_official_alpaca_skills(
    *, project_root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    """Verify the project-local official Alpaca skill files and fingerprints."""
    verified: list[dict[str, str]] = []
    missing: list[str] = []
    for directory, expected_name in REQUIRED_ALPACA_SKILLS.items():
        skill_path = project_root / ".agents" / "skills" / directory / "SKILL.md"
        if not skill_path.is_file():
            missing.append(directory)
            continue
        reference_path = skill_path.with_name("reference.md")
        if not reference_path.is_file():
            missing.append(f"{directory}/reference.md")
            continue
        content = skill_path.read_bytes()
        reference_content = reference_path.read_bytes()
        header = content[:1000].decode("utf-8", errors="replace")
        if f"name: {expected_name}" not in header:
            missing.append(directory)
            continue
        verified.append(
            {
                "skill": expected_name,
                "path": str(skill_path.relative_to(project_root)),
                "sha256": hashlib.sha256(content).hexdigest(),
                "reference_sha256": hashlib.sha256(reference_content).hexdigest(),
            }
        )

    if missing:
        return _failure(
            "official_alpaca_skills",
            "One or more required official Alpaca skills are missing or invalid.",
            missing=missing,
            verified=verified,
        )
    return {
        "component": "official_alpaca_skills",
        "status": "PASS",
        "verified_at": _utc_now(),
        "source": "alpacahq/alpaca-skills",
        "verified": verified,
    }


def run_alpaca_technology_lockbox(
    settings: VolAgentSettings | None = None,
    *,
    cli_verifier: Callable[[VolAgentSettings], dict[str, Any]] = verify_official_alpaca_cli,
    mcp_verifier: Callable[[VolAgentSettings], dict[str, Any]] = verify_official_alpaca_mcp,
    skills_verifier: Callable[..., dict[str, Any]] = verify_official_alpaca_skills,
) -> dict[str, Any]:
    """Run all sponsor-technology proofs and return one sanitized receipt."""
    settings = settings or load_config()
    components = {
        "official_cli": cli_verifier(settings),
        "official_mcp_v2": mcp_verifier(settings),
        "official_skills": skills_verifier(),
    }
    passed = all(component.get("status") == "PASS" for component in components.values())
    return {
        "schema_version": "caisheng.alpaca-lockbox.v1",
        "overall_status": "PASS" if passed else "FAIL",
        "verified_at": _utc_now(),
        "paper_only": True,
        "execution_boundary": (
            "Official CLI/MCP Lockbox checks are read-only; all paper orders remain "
            "behind CaiSheng's canonical approval and broker gateway."
        ),
        "components": components,
    }
