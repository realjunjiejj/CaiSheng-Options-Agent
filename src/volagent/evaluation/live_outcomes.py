"""Persistent, post-event scoring for a live-canary forecast.

The entry artifact is written before the event.  Outcome scoring refuses to run
until the declared exit window has elapsed, preventing post-event information
from contaminating the original decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from volagent.config import ExecutionConfig, PROJECT_ROOT
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.strategies import StrategyCandidate
from volagent.evaluation.accounting_oracle import compute_realized_trade_pnl


LIVE_EVALUATION_DIR = PROJECT_ROOT / "data" / "live_evaluations"


def _safe_event_id(event_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", event_id)


def _path(event_id: str) -> Path:
    return LIVE_EVALUATION_DIR / f"{_safe_event_id(event_id)}.json"


def record_live_forecast(result: dict[str, Any], execution: ExecutionConfig) -> Path:
    """Seal the pre-event market snapshot and forecast before the event occurs."""
    event = result.get("event")
    underlying = result.get("underlying")
    forecast = result.get("move_forecast")
    iv_forecast = result.get("iv_forecast")
    if not event or not underlying or not forecast or not iv_forecast:
        raise ValueError("A complete live forecast is required before it can be evaluated.")

    feature_set = result.get("feature_set", {})
    atm_call = feature_set.get("atm_call")
    atm_put = feature_set.get("atm_put")
    candidate = result.get("approved_candidate")
    payload = {
        "schema_version": 1,
        "kind": "live_pre_event_forecast",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event": event.model_dump(mode="json"),
        "entry_underlying": underlying.model_dump(mode="json"),
        "forecast": forecast.model_dump(mode="json"),
        "iv_forecast": iv_forecast.model_dump(mode="json"),
        "entry_atm": {
            "call": atm_call.model_dump(mode="json") if atm_call else None,
            "put": atm_put.model_dump(mode="json") if atm_put else None,
        },
        "candidate": candidate.model_dump(mode="json") if candidate else None,
        "execution_assumptions": {
            "fee_per_contract": execution.fee_per_contract,
            "slippage_per_contract": execution.slippage_per_contract,
        },
        "decision": getattr(result.get("final_decision"), "value", str(result.get("final_decision"))),
        "risk_status": getattr(getattr(result.get("risk_report"), "overall_status", None), "value", None),
        "outcome": None,
    }
    LIVE_EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    target = _path(event.event_id)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return target


def list_live_forecasts() -> list[dict[str, Any]]:
    """List locally sealed forecast artifacts, newest first."""
    if not LIVE_EVALUATION_DIR.exists():
        return []
    records = []
    for file in LIVE_EVALUATION_DIR.glob("*.json"):
        try:
            payload = json.loads(file.read_text())
            if payload.get("kind") == "live_pre_event_forecast":
                records.append(payload)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(records, key=lambda item: item.get("recorded_at", ""), reverse=True)


def evaluate_live_forecast(
    event_id: str,
    exit_underlying: UnderlyingSnapshot,
    exit_chain: list[OptionContractSnapshot],
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Score a sealed forecast using live post-event quotes and the shared P&L oracle."""
    target = _path(event_id)
    payload = json.loads(target.read_text())
    now = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    event = payload["event"]
    exit_time = datetime.fromisoformat(event["exit_time"]).astimezone(timezone.utc)
    if now < exit_time:
        raise ValueError("Outcome evaluation is unavailable before the declared post-event exit time.")
    if exit_underlying.quote_time.astimezone(timezone.utc) < exit_time:
        raise ValueError("Exit underlying quote predates the declared exit window.")

    entry_spot = float(payload["entry_underlying"]["price"])
    realized_abs_move = abs(exit_underlying.price / entry_spot - 1.0)
    forecast = payload["forecast"]
    iv_forecast = payload["iv_forecast"]
    by_symbol = {contract.symbol: contract for contract in exit_chain}
    entry_atm = payload.get("entry_atm", {})
    atm_exits = [by_symbol.get(item["symbol"]) for item in entry_atm.values() if item]
    if len(atm_exits) != 2 or any(contract is None for contract in atm_exits):
        raise ValueError("Post-event chain is missing one or more sealed ATM contracts.")
    if any(contract.quote_time.astimezone(timezone.utc) < exit_time for contract in atm_exits):
        raise ValueError("Post-event ATM quote predates the declared exit window.")
    exit_atm_iv = sum(float(contract.vendor_implied_vol) for contract in atm_exits) / len(atm_exits)
    entry_atm_iv = sum(float(item["vendor_implied_vol"]) for item in entry_atm.values() if item) / 2.0

    candidate_data = payload.get("candidate")
    pnl: dict[str, Any] | None = None
    if candidate_data:
        candidate = StrategyCandidate.model_validate(candidate_data)
        exit_quotes = {
            leg.contract_symbol: {
                "bid": by_symbol[leg.contract_symbol].bid,
                "ask": by_symbol[leg.contract_symbol].ask,
                "quote_time": by_symbol[leg.contract_symbol].quote_time.isoformat(),
            }
            for leg in candidate.legs
            if leg.contract_symbol in by_symbol
        }
        trade = compute_realized_trade_pnl(
            candidate,
            exit_quotes,
            fee_per_contract=float(payload["execution_assumptions"]["fee_per_contract"]),
            slippage_per_contract=float(payload["execution_assumptions"]["slippage_per_contract"]),
        )
        pnl = {
            "net_pnl": trade.net_pnl,
            "max_loss": trade.max_loss,
            "is_valid": trade.is_valid,
            "validity_note": trade.validity_note,
        }

    outcome = {
        "evaluated_at": now.isoformat(),
        "exit_spot": exit_underlying.price,
        "realized_abs_move_pct": realized_abs_move,
        "median_abs_error_pct": abs(realized_abs_move - float(forecast["median_abs_move_pct"])),
        "implied_move_abs_error_pct": abs(realized_abs_move - float(forecast["implied_move_pct"])),
        "within_q20_q80_interval": float(forecast["q20_abs_move_pct"]) <= realized_abs_move <= float(forecast["q80_abs_move_pct"]),
        "entry_atm_iv": entry_atm_iv,
        "exit_atm_iv": exit_atm_iv,
        "realized_iv_change_points": (exit_atm_iv - entry_atm_iv) * 100.0,
        "iv_change_error_points": abs((exit_atm_iv - entry_atm_iv) * 100.0 - float(iv_forecast["median_iv_change_points"])),
        "paper_trade": pnl,
    }
    payload["outcome"] = outcome
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return outcome
