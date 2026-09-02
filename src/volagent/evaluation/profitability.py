"""Evidence-tiered economic evaluation for CaiSheng.

Synthetic replay, historical bar proxies, and broker-confirmed Alpaca paper
trades answer different questions.  This module deliberately prevents them
from being blended into one headline P&L number.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Mapping


SYNTHETIC_REPLAY = "synthetic_replay"
HISTORICAL_BAR_PROXY = "historical_bar_proxy"
ALPACA_PAPER = "alpaca_paper"
EVIDENCE_TIERS = (SYNTHETIC_REPLAY, HISTORICAL_BAR_PROXY, ALPACA_PAPER)

ALLOWED_CLAIMS = {
    SYNTHETIC_REPLAY: "Controlled synthetic functional replay P&L",
    HISTORICAL_BAR_PROXY: "Historical bar-close premium proxy — non-executable",
    ALPACA_PAPER: "Broker-confirmed Alpaca paper competition P&L",
}


def _mapping_from_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProfitabilityReport:
    """A report whose headline competition result can only use broker fills."""

    starting_nav: float
    competition_pnl: float
    tiers: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "starting_nav": self.starting_nav,
            "competition_pnl": self.competition_pnl,
            "tiers": self.tiers,
        }


def outcomes_from_closed_trades(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Map immutable ledger rows onto broker-evidence profitability outcomes."""
    outcomes: list[dict[str, Any]] = []
    for row in rows:
        raw_payload = _mapping_from_json(row.get("raw_payload"))
        execution_receipt = raw_payload.get("raw_execution_receipt") if isinstance(raw_payload, dict) else {}
        execution_receipt = execution_receipt if isinstance(execution_receipt, dict) else {}
        outcomes.append({
            "trade_id": str(row.get("trade_id", "")),
            "event_id": str(row.get("event_id", "")),
            "symbol": str(row.get("symbol", "")),
            "strategy": str(row.get("decision", "")),
            "closed_at": str(row.get("closed_at", "")),
            "net_pnl": float(row.get("net_realized_pnl_dollars", 0.0)),
            "max_loss": float(row.get("max_loss_budget", 0.0)),
            "evidence_tier": ALPACA_PAPER,
            "entry_order_id": str(row.get("entry_order_id", "")),
            "exit_order_id": str(row.get("exit_order_id", "")),
            "entry_broker_order_id": str(execution_receipt.get("entry_broker_order_id", "")),
            "exit_broker_order_id": str(execution_receipt.get("exit_broker_order_id", "")),
        })
    return outcomes


def _empty_trade_story(unverified_count: int = 0) -> dict[str, Any]:
    return {
        "status": "AWAITING_FIRST_CLOSE" if unverified_count == 0 else "NO_VERIFIED_CLOSE",
        "evidence_label": "ALPACA PAPER · NO BROKER-CONFIRMED CLOSE",
        "what": {
            "headline": "No Alpaca trade closed yet" if unverified_count == 0 else "No verified Alpaca close",
            "detail": "CaiSheng has not completed an eligible broker entry-to-exit lifecycle.",
            "contracts": [],
        },
        "why": {
            "headline": "No execution claim",
            "detail": "Replay decisions are shown separately and never substituted for competition activity.",
        },
        "risk": {
            "headline": "$0 governed risk recorded",
            "detail": "Any untracked broker exposure is reported separately in account truth.",
            "max_loss": 0.0,
            "nav_pct": 0.0,
        },
        "result": {"headline": "$0.00 governed closed-trade P&L", "net_pnl": 0.0, "return_on_risk_pct": 0.0},
        "proof": {"unverified_closed_trades": unverified_count},
    }


def build_latest_trade_story(
    closed_trades: Iterable[Mapping[str, Any]],
    decision_records: Iterable[Mapping[str, Any]],
    orders_by_client_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Join the latest broker-confirmed close into one four-question judge story."""
    decisions = list(decision_records)
    unverified_count = 0
    for trade in sorted(closed_trades, key=lambda row: str(row.get("closed_at", "")), reverse=True):
        raw_trade = _mapping_from_json(trade.get("raw_payload"))
        broker_receipt = raw_trade.get("raw_execution_receipt") or {}
        if not isinstance(broker_receipt, dict):
            broker_receipt = {}
        entry_client_id = str(trade.get("entry_order_id", "")).strip()
        exit_client_id = str(trade.get("exit_order_id", "")).strip()
        entry_broker_id = str(broker_receipt.get("entry_broker_order_id", "")).strip()
        exit_broker_id = str(broker_receipt.get("exit_broker_order_id", "")).strip()
        entry_order = orders_by_client_id.get(entry_client_id) or {}
        exit_order = orders_by_client_id.get(exit_client_id) or {}
        identifiers_valid = (
            entry_client_id
            and exit_client_id
            and entry_client_id != exit_client_id
            and entry_broker_id
            and exit_broker_id
            and entry_broker_id != exit_broker_id
            and str(entry_order.get("broker_order_id", "")) == entry_broker_id
            and str(exit_order.get("broker_order_id", "")) == exit_broker_id
        )
        entry_fill = float(entry_order.get("average_price") or 0.0)
        exit_fill = float(exit_order.get("average_price") or 0.0)
        fills_valid = (
            identifiers_valid
            and math.isfinite(entry_fill)
            and entry_fill > 0.0
            and math.isfinite(exit_fill)
            and exit_fill > 0.0
            and int(entry_order.get("filled_quantity") or 0) > 0
            and int(exit_order.get("filled_quantity") or 0) > 0
            and bool(entry_order.get("filled_at"))
            and bool(exit_order.get("filled_at"))
        )
        if not fills_valid:
            unverified_count += 1
            continue

        event_id = str(trade.get("event_id", ""))
        symbol = str(trade.get("symbol", "UNKNOWN"))
        matched_decision: Mapping[str, Any] = {}
        decision_payload: dict[str, Any] = {}
        for decision in decisions:
            payload = _mapping_from_json(decision.get("raw_payload"))
            snapshot = payload.get("snapshot") or {}
            if (
                str(snapshot.get("event_id", decision.get("event_id", ""))) == event_id
                and str(snapshot.get("symbol", decision.get("symbol", ""))).upper() == symbol.upper()
            ):
                matched_decision = decision
                decision_payload = payload
                break

        volatility = decision_payload.get("volatility_view") or {}
        risk_record = decision_payload.get("risk") or {}
        critic = decision_payload.get("critic") or {}
        forecast_pct = float(volatility.get("expected_move_median_pct") or 0.0) * 100.0
        implied_pct = (
            float(volatility.get("implied_move_bid_pct") or 0.0)
            + float(volatility.get("implied_move_ask_pct") or 0.0)
        ) * 50.0
        equity = float(risk_record.get("current_equity") or 0.0)
        max_loss = float(trade.get("max_loss_budget") or 0.0)
        net_pnl = float(trade.get("net_realized_pnl_dollars") or 0.0)
        entry_plan = _mapping_from_json(entry_order.get("full_order_plan"))
        contracts = [
            str(leg.get("contract_symbol", ""))
            for leg in entry_plan.get("legs", [])
            if isinstance(leg, dict) and leg.get("contract_symbol")
        ]
        strategy = str(trade.get("decision", "UNKNOWN")).split(".")[-1].replace("_", " ").upper()
        nav_pct = max_loss / equity * 100.0 if equity > 0.0 else 0.0
        return_on_risk = float(trade.get("realized_return_pct") or 0.0) * 100.0
        return {
            "status": "BROKER_CONFIRMED",
            "evidence_label": "ALPACA PAPER · BROKER-CONFIRMED CLOSED TRADE",
            "what": {
                "headline": f"{symbol.upper()} · {strategy}",
                "detail": f"{len(contracts)} legs · {int(trade.get('quantity') or 0)} strategy unit",
                "contracts": contracts,
                "entry_fill": entry_fill,
                "exit_fill": exit_fill,
            },
            "why": {
                "headline": f"Forecast ±{forecast_pct:.2f}% vs implied ±{implied_pct:.2f}%",
                "detail": f"Edge {forecast_pct - implied_pct:+.2f} pp · Critic {str(critic.get('recommendation', 'unknown')).upper()}",
                "forecast_move_pct": round(forecast_pct, 4),
                "implied_move_pct": round(implied_pct, 4),
                "edge_percentage_points": round(forecast_pct - implied_pct, 4),
                "decision_hash": str(matched_decision.get("artifact_hash", "")),
            },
            "risk": {
                "headline": f"${max_loss:,.2f} maximum loss",
                "detail": f"{nav_pct:.2f}% of decision-time NAV",
                "max_loss": max_loss,
                "nav_pct": round(nav_pct, 4),
            },
            "result": {
                "headline": f"${net_pnl:+,.2f} net realized P&L",
                "detail": f"{return_on_risk:+.2f}% return on risk · ${float(trade.get('fees_and_slippage') or 0.0):,.2f} costs",
                "net_pnl": net_pnl,
                "gross_pnl": float(trade.get("gross_realized_pnl_dollars") or 0.0),
                "costs": float(trade.get("fees_and_slippage") or 0.0),
                "return_on_risk_pct": return_on_risk,
                "holding_hours": float(trade.get("holding_hours") or 0.0),
            },
            "proof": {
                "trade_id": str(trade.get("trade_id", "")),
                "entry_client_order_id": entry_client_id,
                "exit_client_order_id": exit_client_id,
                "entry_broker_order_id": entry_broker_id,
                "exit_broker_order_id": exit_broker_id,
                "entry_filled_at": str(entry_order.get("filled_at", "")),
                "exit_filled_at": str(exit_order.get("filled_at", "")),
            },
        }
    return _empty_trade_story(unverified_count)


def _currency_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace("$", "").replace(",", "").replace("+", "").strip())


def outcomes_from_replay_results(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map only valid CaiSheng Full replay trades onto synthetic evidence."""
    outcomes: list[dict[str, Any]] = []
    for index, row in enumerate(results.get("rows", []), start=1):
        full = row.get("volagent") or {}
        decision = str(full.get("decision", "no_trade"))
        status = str(full.get("status", ""))
        if decision == "no_trade" or not status.startswith("VALID"):
            continue
        outcomes.append({
            "trade_id": f"replay-{index}",
            "event_id": str(row.get("scenario_id") or row.get("scenario") or f"scenario-{index}"),
            "symbol": str((row.get("underlying") or {}).get("symbol") or row.get("symbol") or "UNKNOWN"),
            "strategy": decision,
            "closed_at": str((row.get("event") or {}).get("event_time") or index),
            "net_pnl": float(full.get("pnl_value", 0.0)),
            "max_loss": _currency_value(full.get("max_loss_value", full.get("max_loss", 0.0))),
            "evidence_tier": SYNTHETIC_REPLAY,
        })
    return outcomes


def build_economic_evidence(
    *,
    replay_results: Mapping[str, Any] | None,
    historical_results: Mapping[str, Any] | None,
    closed_trades: Iterable[Mapping[str, Any]],
    starting_nav: float = 100_000.0,
    current_equity: float | None = None,
) -> dict[str, Any]:
    """Build a canonical judge receipt from existing evidence sources."""
    outcomes = outcomes_from_replay_results(replay_results or {})
    outcomes.extend(outcomes_from_closed_trades(closed_trades))
    profitability = build_profitability_report(outcomes, starting_nav=starting_nav).to_dict()
    paper = profitability["tiers"][ALPACA_PAPER]
    historical_summary = dict((historical_results or {}).get("summary") or {})

    verified_equity = (
        float(current_equity)
        if current_equity is not None and math.isfinite(float(current_equity)) and float(current_equity) > 0.0
        else None
    )
    governed_closed_trade_pnl = round(float(profitability["competition_pnl"]), 2)
    full_account_net_pnl = (
        round(verified_equity - float(starting_nav), 2)
        if verified_equity is not None
        else None
    )
    full_account_return_pct = (
        round(full_account_net_pnl / float(starting_nav) * 100.0, 4)
        if full_account_net_pnl is not None and float(starting_nav) > 0.0
        else None
    )
    unattributed_difference = (
        round(full_account_net_pnl - governed_closed_trade_pnl, 2)
        if full_account_net_pnl is not None
        else None
    )
    receipt: dict[str, Any] = {
        "schema_version": "caisheng.economic_evidence.v1",
        "claim_policy": {
            "competition_pnl_source": "broker-confirmed closed Alpaca paper trades only",
            "account_truth_source": "current Alpaca paper equity minus immutable starting NAV",
            "historical_scope": "forecast validation; historical option bars are non-executable proxies",
            "synthetic_scope": "controlled functional replay; not evidence of predictive alpha",
        },
        "competition": {
            "starting_nav": float(starting_nav),
            "current_equity": verified_equity,
            # `realized_pnl` is retained as a backward-compatible alias for the
            # governed closed-trade subset. The full-account fields are the
            # headline truth and include activity outside CaiSheng's ledger.
            "realized_pnl": governed_closed_trade_pnl,
            "governed_closed_trade_pnl": governed_closed_trade_pnl,
            "full_account_net_pnl": full_account_net_pnl,
            "full_account_return_pct": full_account_return_pct,
            "unattributed_and_unrealized_difference": unattributed_difference,
            "closed_trades_count": paper["trades_count"],
            "status": (
                "BROKER_CONFIRMED_CLOSED_TRADES_AVAILABLE"
                if paper["trades_count"] > 0
                else "AWAITING_BROKER_CONFIRMED_CLOSED_TRADES"
            ),
        },
        "profitability": profitability,
        "historical_predictive_validation": historical_summary,
    }
    receipt["receipt_hash"] = _canonical_hash(receipt)
    return receipt


def write_economic_evidence_receipt(receipt: Mapping[str, Any], output_path: str | Path) -> Path:
    """Atomically persist a canonical economic-evidence receipt."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(receipt), indent=2) + "\n")
    temporary.replace(path)
    return path


def build_current_economic_evidence() -> dict[str, Any]:
    """Build the receipt from CaiSheng's current replay, OOS, and ledger state."""
    from volagent.evaluation.evaluator import evaluate_benchmarks
    from volagent.execution.ledger import ExecutionLedger

    project_root = Path(__file__).resolve().parents[3]
    historical_path = project_root / "data" / "evaluation" / "oos_evaluation_results.json"
    try:
        historical = json.loads(historical_path.read_text())
    except (OSError, json.JSONDecodeError):
        historical = {}

    ledger = ExecutionLedger()
    metadata = ledger.get_or_init_competition_metadata(starting_nav=100_000.0)
    snapshot = ledger.get_latest_portfolio_snapshot()
    current_equity = None
    if snapshot and not snapshot.get("is_stale"):
        current_equity = snapshot.get("equity")
    return build_economic_evidence(
        replay_results=evaluate_benchmarks(),
        historical_results=historical,
        closed_trades=ledger.list_closed_trades(),
        starting_nav=float(metadata.get("starting_nav", 100_000.0)),
        current_equity=current_equity,
    )


def _economic_metrics(records: list[dict[str, Any]], starting_nav: float) -> dict[str, Any]:
    """Compute closed-trade economics from a single evidence tier."""
    if not records:
        return {
            "return_on_starting_nav_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": None,
            "average_trade_pnl": 0.0,
            "return_on_total_max_risk_pct": 0.0,
            "max_drawdown_dollars": 0.0,
            "max_drawdown_pct": 0.0,
            "cvar_95_dollars": None,
            "mean_trade_pnl_bootstrap_95ci": None,
            "bootstrap_method": "cluster bootstrap by close date; deterministic seed 42",
        }

    pnls = [record["net_pnl"] for record in records]
    risks = [record["max_loss"] for record in records]
    net_pnl = sum(pnls)
    gross_profit = sum(pnl for pnl in pnls if pnl > 0.0)
    gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0.0))
    total_risk = sum(risks)

    equity = starting_nav
    high_water = starting_nav
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for record in sorted(records, key=lambda item: (item["closed_at"], item["trade_id"])):
        equity += record["net_pnl"]
        high_water = max(high_water, equity)
        drawdown = high_water - equity
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown / high_water * 100.0)

    tail_count = max(1, math.ceil(len(pnls) * 0.05))
    cvar_95 = sum(sorted(pnls)[:tail_count]) / tail_count
    by_date: dict[str, list[float]] = {}
    for record in records:
        by_date.setdefault(record["closed_at"][:10], []).append(record["net_pnl"])
    groups = list(by_date.values())
    rng = random.Random(42)
    bootstrap_means: list[float] = []
    for _ in range(2_000):
        sampled = [groups[rng.randrange(len(groups))] for _ in groups]
        flattened = [pnl for group in sampled for pnl in group]
        bootstrap_means.append(sum(flattened) / len(flattened))
    bootstrap_means.sort()
    low = bootstrap_means[math.floor(0.025 * (len(bootstrap_means) - 1))]
    high = bootstrap_means[math.ceil(0.975 * (len(bootstrap_means) - 1))]
    return {
        "return_on_starting_nav_pct": round(net_pnl / starting_nav * 100.0, 6),
        "win_rate_pct": round(sum(pnl > 0.0 for pnl in pnls) / len(pnls) * 100.0, 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else None,
        "average_trade_pnl": round(net_pnl / len(pnls), 2),
        "return_on_total_max_risk_pct": round(net_pnl / total_risk * 100.0, 6) if total_risk > 0.0 else 0.0,
        "max_drawdown_dollars": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 6),
        "cvar_95_dollars": round(cvar_95, 2),
        "mean_trade_pnl_bootstrap_95ci": [round(low, 2), round(high, 2)],
        "bootstrap_method": "cluster bootstrap by close date; deterministic seed 42",
    }


def build_profitability_report(
    outcomes: Iterable[Mapping[str, Any]],
    starting_nav: float = 100_000.0,
) -> ProfitabilityReport:
    """Aggregate closed outcomes without crossing evidence boundaries."""
    if not math.isfinite(starting_nav) or starting_nav <= 0.0:
        raise ValueError("starting_nav must be positive and finite")

    tiers = {
        tier: {
            "allowed_claim": ALLOWED_CLAIMS[tier],
            "trades_count": 0,
            "excluded_count": 0,
            "net_pnl": 0.0,
            "status": "NO_EVIDENCE",
        }
        for tier in EVIDENCE_TIERS
    }
    accepted: dict[str, list[dict[str, Any]]] = {tier: [] for tier in EVIDENCE_TIERS}
    for raw in outcomes:
        tier = str(raw.get("evidence_tier", ""))
        if tier not in tiers:
            raise ValueError(f"Unsupported evidence tier: {tier or '<missing>'}")
        pnl = float(raw.get("net_pnl", 0.0))
        if not math.isfinite(pnl):
            raise ValueError("net_pnl must be finite")
        max_loss = float(raw.get("max_loss", 0.0))
        if not math.isfinite(max_loss) or max_loss < 0.0:
            raise ValueError("max_loss must be non-negative and finite")
        if tier == ALPACA_PAPER:
            entry_order_id = str(raw.get("entry_order_id", "")).strip()
            exit_order_id = str(raw.get("exit_order_id", "")).strip()
            entry_broker_order_id = str(raw.get("entry_broker_order_id", "")).strip()
            exit_broker_order_id = str(raw.get("exit_broker_order_id", "")).strip()
            if (
                not entry_order_id
                or not exit_order_id
                or entry_order_id == exit_order_id
                or not entry_broker_order_id
                or not exit_broker_order_id
                or entry_broker_order_id == exit_broker_order_id
            ):
                tiers[tier]["excluded_count"] += 1
                tiers[tier]["status"] = "NO_BROKER_CONFIRMED_CLOSED_TRADES"
                continue
        accepted[tier].append({
            "trade_id": str(raw.get("trade_id", "")),
            "closed_at": str(raw.get("closed_at", "")),
            "net_pnl": pnl,
            "max_loss": max_loss,
        })
        tiers[tier]["trades_count"] += 1
        tiers[tier]["net_pnl"] = round(tiers[tier]["net_pnl"] + pnl, 2)
        tiers[tier]["status"] = "EVIDENCE_AVAILABLE"

    for tier in EVIDENCE_TIERS:
        tiers[tier].update(_economic_metrics(accepted[tier], starting_nav))

    return ProfitabilityReport(
        starting_nav=float(starting_nav),
        competition_pnl=float(tiers[ALPACA_PAPER]["net_pnl"]),
        tiers=tiers,
    )
