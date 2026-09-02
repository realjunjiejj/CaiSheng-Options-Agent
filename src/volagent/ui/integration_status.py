"""Small, sanitized integration proofs for the judge-facing UI."""

from __future__ import annotations

from typing import Any, Protocol


PRIMARY_WORKSPACES = ("Overview", "Agent", "Operations", "Results")
PUBLIC_JUDGE_WORKSPACES = ("Overview", "Agent", "Results")


def judge_workspaces(*, public_read_only: bool) -> tuple[str, ...]:
    """Expose only credential-free surfaces in the public Cloud Run app."""
    return PUBLIC_JUDGE_WORKSPACES if public_read_only else PRIMARY_WORKSPACES


class MCPReadService(Protocol):
    """Narrow seam used by the UI and tests without coupling to FastMCP internals."""

    ledger: Any

    def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        decision_id: str | None = None,
    ) -> dict[str, Any]: ...


def sanitize_preflight_for_judges(receipt: dict[str, Any]) -> dict[str, Any]:
    """Return only non-sensitive facts needed to prove the Alpaca preflight."""
    account = receipt.get("account") or {}
    checks = receipt.get("checks") or []
    return {
        "overall_status": receipt.get("overall_status", "HALTED"),
        "generated_at": receipt.get("generated_at"),
        "checks": [
            {
                "check": check.get("check"),
                "status": check.get("status", "FAIL"),
            }
            for check in checks
            if isinstance(check, dict)
        ],
        "account": {
            "equity": account.get("equity"),
            "buying_power": account.get("buying_power"),
            "paper_endpoint": account.get("paper_endpoint"),
        },
    }


def run_mcp_read_verification(service: MCPReadService) -> dict[str, Any]:
    """Exercise two read-only MCP gateway tools and return a sanitized receipt."""
    responses: dict[str, dict[str, Any]] = {}
    for tool_name in ("alpaca_get_account", "alpaca_get_market_clock"):
        try:
            responses[tool_name] = service.handle_tool_call(tool_name, {})
        except Exception as exc:  # UI proof must fail closed, never crash the cockpit.
            responses[tool_name] = {
                "status": "ERROR",
                "call_id": None,
                "result": {"error_type": type(exc).__name__},
            }

    account_response = responses["alpaca_get_account"]
    clock_response = responses["alpaca_get_market_clock"]
    account = account_response.get("result") or {}
    clock = clock_response.get("result") or {}
    passed = all(response.get("status") == "SUCCESS" for response in responses.values())

    try:
        audit_event_count = len(service.ledger.list_mcp_audit_events())
    except Exception:
        audit_event_count = 0

    return {
        "overall_status": "PASS" if passed else "FAIL",
        "tools": {
            name: {
                "status": response.get("status", "ERROR"),
                "call_id": response.get("call_id"),
            }
            for name, response in responses.items()
        },
        "account": {
            "equity": account.get("equity"),
            "buying_power": account.get("buying_power"),
            "as_of_time": account.get("as_of_time"),
        },
        "market_clock": {
            "is_open": clock.get("is_open"),
            "next_open": clock.get("next_open"),
            "next_close": clock.get("next_close"),
            "timestamp": clock.get("timestamp"),
        },
        "audit_event_count": audit_event_count,
        "transport_note": "CaiSheng MCP gateway; Streamable HTTP is served at /mcp.",
    }
