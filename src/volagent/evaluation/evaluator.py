"""Controlled, reproducible component-ablation and benchmark evaluation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from volagent.config import VolAgentSettings, load_config
from volagent.data.replay import REPLAY_DIR, ReplayDataManager
from volagent.domain.enums import AbstentionReason, Decision, GateStatus
from volagent.domain.strategies import StrategyCandidate
from volagent.evaluation.accounting_oracle import RealizedTradeResult, compute_realized_trade_pnl
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.builder import VolAgentWorkflow


FULL = "CaiSheng (Full)"
B0 = "B0: NO_TRADE"
B1 = "B1: ALWAYS_LONG_STRADDLE"
B2 = "B2: ALWAYS_SHORT_IRON_BUTTERFLY"
B3 = "B3: FINAL_GOVERNOR_OFF"
B4 = "B4: QUANT_ONLY"
MODEL_NAMES = [FULL, B0, B1, B2, B3, B4]

VARIANT_CONTROLS = [
    {"Model": FULL, "Quant Pipeline": "ON", "Agent Debate": "ON", "Safety Critic": "ON", "Final Governor": "ON"},
    {"Model": B3, "Quant Pipeline": "ON", "Agent Debate": "ON", "Safety Critic": "ON", "Final Governor": "OFF"},
    {"Model": B4, "Quant Pipeline": "ON", "Agent Debate": "OFF", "Safety Critic": "DETERMINISTIC", "Final Governor": "ON"},
]


def _empty_result() -> dict[str, Any]:
    return {
        "rows": [],
        "ablation_table": [],
        "summary": [],
        "variant_controls": VARIANT_CONTROLS,
        "evaluation_errors": [],
        "total_scenarios": 0,
        "declared_scenarios": 0,
    }


def _candidate_for(result: dict[str, Any], decision: Decision) -> StrategyCandidate | None:
    return next((candidate for candidate in result.get("candidates", []) if candidate.decision == decision), None)


def _abstention_text(value: Any) -> str:
    if value in (None, AbstentionReason.NONE):
        return "none"
    return value.value if hasattr(value, "value") else str(value)


def _first_failed_check(result: dict[str, Any]) -> str:
    report = result.get("risk_report")
    if report is None:
        return "unknown"
    failed = [check.name for check in report.checks if check.status == GateStatus.FAIL]
    return failed[0] if failed else "none"


def _format_trade(trade: RealizedTradeResult) -> tuple[str, str, str, str]:
    pnl = f"${trade.net_pnl:+.2f}" if trade.net_pnl is not None else "N/A"
    return trade.entry_description, trade.exit_description, pnl, f"${trade.max_loss:.2f}"


def evaluate_benchmarks(
    data_dir: Path | str = REPLAY_DIR,
    config: VolAgentSettings | None = None,
    llm_client: Any = None,
) -> dict[str, Any]:
    """Evaluate controlled graph variants and naive strategy baselines.

    Full, B3, and B4 execute the same compiled LangGraph. Only the state flags
    documented in ``VARIANT_CONTROLS`` differ. B1 and B2 reuse the exact
    contracts, sizing, repricing, seed, and filtered chain produced by Full.
    """
    data_path = Path(data_dir)
    manifest_file = data_path / "manifest.json"
    if not manifest_file.exists():
        return _empty_result()

    try:
        manifest = json.loads(manifest_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        result = _empty_result()
        result["evaluation_errors"] = [{"scenario_id": "manifest", "error": str(exc)}]
        return result

    scenarios = manifest.get("scenarios", [])
    if not scenarios:
        return _empty_result()

    cfg = (config or load_config()).model_copy(deep=True)
    # Judge replay uses a fixed, seeded scenario budget. It preserves variant
    # comparability while keeping cold-start latency bounded.
    cfg.forecast.monte_carlo_scenarios = min(cfg.forecast.monte_carlo_scenarios, 256)
    replay_mgr = ReplayDataManager(data_dir=data_path)
    workflow = VolAgentWorkflow(config=cfg, llm_client=llm_client)
    evaluation_workspace = tempfile.TemporaryDirectory(prefix="caisheng-replay-evaluation-")
    evaluation_ledger = ExecutionLedger(
        db_path=Path(evaluation_workspace.name) / "evaluation.db"
    )

    aggregates = {
        name: {
            "valid_trades": 0,
            "invalid_attempts": 0,
            "abstentions": 0,
            "risk_breaches": 0,
            "executable_pnl": 0.0,
        }
        for name in MODEL_NAMES
    }
    rows: list[dict[str, Any]] = []
    ablation_table: list[dict[str, Any]] = []
    evaluation_errors: list[dict[str, str]] = []

    for scenario_info in scenarios:
        scenario_id = scenario_info.get("scenario_id") or scenario_info.get("symbol")
        try:
            scenario = replay_mgr.load_scenario(scenario_id)
        except Exception as exc:
            evaluation_errors.append({"scenario_id": str(scenario_id), "error": str(exc)})
            continue

        underlying = scenario["underlying"]
        event = scenario["event"]
        exit_quotes = scenario.get("sealed_outcomes", {}).get("exit_option_quotes", {})
        assumptions = scenario.get("execution_assumptions", {})
        fee = float(assumptions.get("fee_per_contract", cfg.execution.fee_per_contract))
        slippage = float(assumptions.get("slippage_per_contract", cfg.execution.slippage_per_contract))
        multiplier = int(assumptions.get("multiplier", 100))

        graph_inputs = {
            "scenario_id": scenario_id,
            "underlying": underlying,
            "event": event,
            "option_chain": scenario["option_chain"],
            "evidence": scenario.get("evidence", []),
            "historical_moves": scenario.get("historical_moves", []),
            "ledger": evaluation_ledger,
        }
        full_result = workflow.run({**graph_inputs, "enable_agent_debate": True, "enable_risk_governor": True})
        b3_result = workflow.run({**graph_inputs, "enable_agent_debate": True, "enable_risk_governor": False})
        b4_result = workflow.run({**graph_inputs, "enable_agent_debate": False, "enable_risk_governor": True})

        full_candidate = full_result.get("approved_candidate")
        b3_candidate = b3_result.get("approved_candidate")
        b4_candidate = b4_result.get("approved_candidate")
        b1_candidate = _candidate_for(full_result, Decision.LONG_STRADDLE)
        b2_candidate = _candidate_for(full_result, Decision.SHORT_IRON_BUTTERFLY)

        model_inputs = {
            FULL: {
                "decision": full_result.get("final_decision", Decision.NO_TRADE),
                "candidate": full_candidate,
                "abstention": _abstention_text(full_result.get("abstention_reason")),
                "governor_bypassed": False,
                "risk_reason": _first_failed_check(full_result),
            },
            B0: {
                "decision": Decision.NO_TRADE,
                "candidate": None,
                "abstention": "unconditionally_flat",
                "governor_bypassed": False,
                "risk_reason": "none",
            },
            B1: {
                "decision": Decision.LONG_STRADDLE if b1_candidate else Decision.NO_TRADE,
                "candidate": b1_candidate,
                "abstention": "missing_shared_candidate" if b1_candidate is None else "none",
                "governor_bypassed": b1_candidate is not None and not event.confirmed,
                "risk_reason": "event_timing" if b1_candidate is not None and not event.confirmed else "none",
            },
            B2: {
                "decision": Decision.SHORT_IRON_BUTTERFLY if b2_candidate else Decision.NO_TRADE,
                "candidate": b2_candidate,
                "abstention": "missing_shared_candidate" if b2_candidate is None else "none",
                "governor_bypassed": b2_candidate is not None and not event.confirmed,
                "risk_reason": "event_timing" if b2_candidate is not None and not event.confirmed else "none",
            },
            B3: {
                "decision": b3_result.get("final_decision", Decision.NO_TRADE),
                "candidate": b3_candidate,
                "abstention": _abstention_text(b3_result.get("abstention_reason")),
                "governor_bypassed": bool(b3_result.get("governor_bypassed")),
                "risk_reason": _first_failed_check(b3_result),
            },
            B4: {
                "decision": b4_result.get("final_decision", Decision.NO_TRADE),
                "candidate": b4_candidate,
                "abstention": _abstention_text(b4_result.get("abstention_reason")),
                "governor_bypassed": False,
                "risk_reason": _first_failed_check(b4_result),
            },
        }

        scenario_output: dict[str, Any] = {
            "scenario": f"{underlying.symbol} - {scenario_info.get('description', scenario_id)}",
            "symbol": underlying.symbol,
            "underlying_price": underlying.price,
            "exit_spot": scenario.get("sealed_outcomes", {}).get("exit_spot", underlying.price),
        }

        for model_name in MODEL_NAMES:
            model = model_inputs[model_name]
            decision: Decision = model["decision"]
            candidate: StrategyCandidate | None = model["candidate"]
            bypassed = bool(model["governor_bypassed"])
            risk_reason = str(model["risk_reason"])

            if candidate is None or decision == Decision.NO_TRADE:
                aggregates[model_name]["abstentions"] += 1
                entry, exit_value, pnl, max_loss = "—", "—", "$0.00", "$0.00"
                pnl_value: float | None = 0.0
                breach = "No"
                validity = "VALID (Flat)"
                if model_name in (FULL, B4) and risk_reason != "none":
                    validity = "VALID (Risk Veto)"
                elif model_name == B3 and risk_reason != "none":
                    validity = "VALID (Upstream Veto)"
            else:
                trade = compute_realized_trade_pnl(
                    candidate,
                    exit_quotes,
                    fee_per_contract=fee,
                    slippage_per_contract=slippage,
                    multiplier=multiplier,
                    expected_exit_time=event.exit_time,
                )
                entry, exit_value, pnl, max_loss = _format_trade(trade)
                pnl_value = trade.net_pnl
                breach = f"Yes ({risk_reason})" if bypassed else "No"
                if bypassed:
                    aggregates[model_name]["risk_breaches"] += 1
                if trade.is_valid and trade.net_pnl is not None:
                    aggregates[model_name]["valid_trades"] += 1
                    aggregates[model_name]["executable_pnl"] += trade.net_pnl
                    validity = "COUNTERFACTUAL (Policy Bypassed)" if bypassed else "VALID"
                else:
                    aggregates[model_name]["invalid_attempts"] += 1
                    validity = trade.validity_note

            table_row = {
                "Scenario": f"{underlying.symbol} ({scenario_info.get('description', scenario_id)})",
                "Model": model_name,
                "Decision": decision.value,
                "Net P&L": pnl,
                "Max Loss": max_loss,
                "Risk Breach": breach,
                "Execution Validity": validity,
                "Abstention Reason": model["abstention"],
                "Entry": entry,
                "Exit": exit_value,
                "pnl_value": pnl_value,
            }
            ablation_table.append(table_row)

            compact_key = {
                FULL: "volagent",
                B0: "b0",
                B1: "b1",
                B2: "b2",
                B3: "b3",
                B4: "b4",
            }[model_name]
            scenario_output[compact_key] = {
                "decision": decision.value,
                "pnl": pnl,
                "pnl_value": pnl_value,
                "max_loss": max_loss,
                "status": validity,
                "breach": breach,
            }

        rows.append(scenario_output)

    evaluated_count = len(rows)
    agent_label = "LLM-backed structured debate" if llm_client is not None else "Deterministic replay-agent debate"
    roles = {
        FULL: f"{agent_label} + shared quant pipeline + deterministic safety stack",
        B0: "Unconditionally flat null benchmark",
        B1: "Always chooses the shared long-straddle candidate",
        B2: "Always chooses the shared short-iron-butterfly candidate",
        B3: "Controlled ablation: only the final deterministic governor is disabled",
        B4: "Controlled ablation: agent debate disabled; deterministic critic and governor retained",
    }
    summary = []
    for model_name in MODEL_NAMES:
        aggregate = aggregates[model_name]
        summary.append({
            "Model Benchmark": model_name,
            "Valid Trades": f"{aggregate['valid_trades']}/{evaluated_count}",
            "Invalid Attempts": f"{aggregate['invalid_attempts']}/{evaluated_count}",
            "Abstentions": f"{aggregate['abstentions']}/{evaluated_count}",
            "Risk Breaches": str(aggregate["risk_breaches"]),
            "Executable Net P&L": f"${aggregate['executable_pnl']:+.2f}",
            "Component Role": roles[model_name],
            "pnl_value": round(aggregate["executable_pnl"], 2),
            "risk_breaches_value": aggregate["risk_breaches"],
            "valid_trades_value": aggregate["valid_trades"],
        })

    result = {
        "rows": rows,
        "ablation_table": ablation_table,
        "summary": summary,
        "variant_controls": VARIANT_CONTROLS,
        "evaluation_errors": evaluation_errors,
        "total_scenarios": evaluated_count,
        "declared_scenarios": len(scenarios),
        "agent_mode": "llm" if llm_client is not None else "deterministic_replay",
        "monte_carlo_scenarios": cfg.forecast.monte_carlo_scenarios,
    }
    evaluation_workspace.cleanup()
    return result
