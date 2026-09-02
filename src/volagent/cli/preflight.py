"""Alpaca Operations Proof: Preflight Verification CLI & Receipt Generator."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from volagent.config import MandateConfig, VolAgentSettings, load_config
from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
from volagent.execution.ledger import ExecutionLedger


def run_cli_preflight(
    settings: VolAgentSettings | None = None,
    ledger: ExecutionLedger | None = None,
    portfolio_adapter: AlpacaPortfolioAdapter | None = None,
    output_path: Path | str = "data/evaluation/preflight_receipt.json",
) -> dict[str, Any]:
    """Execute operational preflight verification and export sanitized JSON receipt."""
    settings = settings or load_config()
    ledger = ledger or ExecutionLedger()
    portfolio_adapter = portfolio_adapter or AlpacaPortfolioAdapter(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=settings.alpaca_paper_trade,
    )

    checks: list[dict[str, Any]] = []
    overall_status = "CLEAN"

    # 1. Paper Endpoint Check
    paper_ok = settings.alpaca_paper_trade is True
    checks.append({
        "check": "paper_trading_mode",
        "status": "PASS" if paper_ok else "FAIL",
        "details": "Paper trading endpoint strictly enforced (no live money)",
    })
    if not paper_ok:
        overall_status = "HALTED"

    # 2. Account Accessibility, Authentication & Snapshot Check
    snapshot_ok = False
    equity = 0.0
    cash = 0.0
    bp = 0.0
    account_id = None
    try:
        snap = portfolio_adapter.fetch_portfolio_snapshot(ledger=ledger)
        equity = snap.equity
        cash = snap.cash
        bp = snap.buying_power
        account_id = snap.account_id
        
        # Strict validation: Must not be stale, must have positive equity, finite buying power, and valid account ID
        has_auth = bool(settings.alpaca_api_key and settings.alpaca_secret_key)
        snapshot_ok = (
            has_auth
            and not snap.is_stale
            and equity > 0
            and math.isfinite(equity)
            and bp >= 0
            and math.isfinite(bp)
            and account_id is not None
            and len(account_id) > 0
        )
        
        if snapshot_ok:
            checks.append({
                "check": "account_accessibility",
                "status": "PASS",
                "details": f"Authenticated Paper Account ({account_id}); Equity=${equity:,.2f}, Cash=${cash:,.2f}, Buying Power=${bp:,.2f}",
            })
        else:
            reason = snap.last_error if hasattr(snap, "last_error") else portfolio_adapter.last_error or "Account snapshot stale or unauthenticated"
            checks.append({
                "check": "account_accessibility",
                "status": "FAIL",
                "details": f"Account unauthenticated or invalid: {reason}",
            })
            overall_status = "HALTED"
    except Exception as exc:
        checks.append({
            "check": "account_accessibility",
            "status": "FAIL",
            "details": f"Failed to fetch account snapshot: {exc}",
        })
        overall_status = "HALTED"

    # 3. Initial Balance Metadata Check ($100,000)
    try:
        meta = ledger.get_or_init_competition_metadata(
            starting_nav=MandateConfig().competition_initial_nav,
            paper_account_id=account_id,
        )
        meta_ok = (
            (meta.get("starting_nav") == 100_000.0 or meta.get("initial_nav") == 100_000.0)
            and (not account_id or meta.get("paper_account_id") == account_id)
        )
        meta_detail = (
            f"Competition initial NAV verified at "
            f"${meta.get('starting_nav', meta.get('initial_nav', 0)):,.2f}; "
            f"paper account binding={meta.get('paper_account_id') or 'pending'}"
        )
    except Exception as exc:
        meta = {}
        meta_ok = False
        meta_detail = f"Competition metadata/account binding failed: {exc}"
    checks.append({
        "check": "competition_metadata",
        "status": "PASS" if meta_ok else "FAIL",
        "details": meta_detail,
    })
    if not meta_ok:
        overall_status = "HALTED"

    # 4. Runtime Halt State Check
    is_halted, halt_reason = ledger.is_system_halted()
    if is_halted:
        checks.append({
            "check": "halt_state",
            "status": "FAIL",
            "details": f"Active system halt: {halt_reason or 'Unknown'}",
        })
        overall_status = "HALTED"
    else:
        checks.append({
            "check": "halt_state",
            "status": "PASS",
            "details": "No active system halt detected",
        })

    receipt = {
        "receipt_type": "caisheng.preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "account": {
            "account_id": account_id,
            "equity": equity,
            "cash": cash,
            "buying_power": bp,
            "paper_endpoint": "https://paper-api.alpaca.markets",
        },
        "checks": checks,
    }

    # Save to disk
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(receipt, indent=2) + "\n")

    return receipt
