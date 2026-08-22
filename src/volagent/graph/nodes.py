"""LangGraph graph node implementations with strict trust boundaries and fail-closed routing."""

from datetime import datetime, timezone
import uuid
from typing import Any

from volagent.agents.event_magnitude import run_event_magnitude_agent
from volagent.agents.long_vol import run_long_vol_advocate, run_short_vol_advocate
from volagent.agents.model_risk import run_model_risk_critic
from volagent.config import VolAgentSettings
from volagent.data.replay import ReplayDataManager
from volagent.domain.enums import AbstentionReason, DataMode, Decision, GateStatus, RunStatus
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.state import VolAgentState
from volagent.quant.expected_move import compute_implied_move
from volagent.quant.features import build_quantitative_features
from volagent.quant.forecast import compute_shrinkage_forecast
from volagent.quant.quote_filters import filter_option_chain
from volagent.quant.repricing import reprice_strategy_monte_carlo
from volagent.quant.risk_gate import evaluate_risk_gate
from volagent.quant.strategy_factory import (
    build_long_straddle_candidate,
    build_short_iron_butterfly_candidate,
)
from volagent.quant.strategy_selector import select_best_strategy
from volagent.quant.surface import compute_surface_quality, find_atm_contracts, select_best_expiration


def initialize_run(state: VolAgentState, agent_settings: VolAgentSettings) -> dict[str, Any]:
    """Initialize state, generate run_id and setup trace events."""
    run_id = state.get("run_id") or f"run-{uuid.uuid4().hex[:8]}"
    return {
        "run_id": run_id,
        "status": RunStatus.ANALYZING,
        "final_decision": Decision.NO_TRADE,
        "abstention_reason": AbstentionReason.NONE,
        "approved_candidate": None,
        "audit_proposal": None,
        "trace_events": [{
            "node": "initialize_run",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Initialized run {run_id}",
        }],
    }


def fetch_market_snapshot(state: VolAgentState, agent_settings: VolAgentSettings) -> dict[str, Any]:
    """Fetch point-in-time snapshot, option chain, and evidence for symbol or scenario."""
    symbol = state.get("symbol", "NVDA")
    scenario_id = agent_settings.volagent_replay_scenario_id or f"SCENARIO-{symbol}"

    replay_mgr = ReplayDataManager()
    scenario_data = replay_mgr.load_scenario(scenario_id)

    evidence = scenario_data.get("evidence_items") or scenario_data.get("evidence", [])

    return {
        "underlying": scenario_data["underlying"],
        "event": scenario_data["event"],
        "option_chain": scenario_data["option_chain"],
        "evidence": evidence,
        "feature_set": {"historical_moves": scenario_data.get("historical_moves", [0.08, 0.05, 0.12, 0.06])},
        "artifact_hashes": {"scenario_file": scenario_data.get("file_hash", "")},
        "trace_events": [{
            "node": "fetch_market_snapshot",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Fetched {len(scenario_data['option_chain'])} option quotes and {len(evidence)} evidence items",
        }],
    }


def event_magnitude_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Event Magnitude Agent in parallel with Vol Quant."""
    event = state.get("event")
    evidence = state.get("evidence", [])

    if not event:
        return {}

    assessment = run_event_magnitude_agent(event, evidence, llm_client=llm_client)

    return {
        "event_assessment": assessment,
        "trace_events": [{
            "node": "event_magnitude_agent",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Event uncertainty score: {assessment.magnitude_pressure_score:.2f}, Novelty: {assessment.event_novelty_score:.2f}",
        }],
    }


def volatility_quant_node(state: VolAgentState, agent_settings: VolAgentSettings) -> dict[str, Any]:
    """Run deterministic volatility surface calculations with fail-closed safety."""
    underlying = state.get("underlying")
    event = state.get("event")
    chain = state.get("option_chain", [])

    if not chain or not underlying or not event:
        return {
            "final_decision": Decision.NO_TRADE,
            "abstention_reason": AbstentionReason.DATA_QUALITY,
            "rejection_reasons": ["Empty options chain or missing market data provided"],
            "feature_set": {"implied_metrics": None},
        }

    # Expiration selection
    expirations = list(set(c.expiration for c in chain))
    best_exp = select_best_expiration(expirations, event.event_time.date(), agent_settings.contracts, chain)

    # Filter quotes with one-sided quote_time check
    filtered_chain, audit = filter_option_chain(
        chain=chain,
        target_symbol=underlying.symbol,
        target_expiration=best_exp,
        as_of_time=underlying.quote_time,
        config=agent_settings.contracts,
    )

    # Find ATM contracts
    atm_call, atm_put, atm_strike = find_atm_contracts(filtered_chain, underlying.price)
    surface_quality = compute_surface_quality(filtered_chain, underlying.price)

    implied_metrics = None
    if atm_call and atm_put:
        implied_metrics = compute_implied_move(atm_call, atm_put, underlying.price)

    return {
        "option_chain": filtered_chain,
        "feature_set": {
            "atm_call": atm_call,
            "atm_put": atm_put,
            "atm_strike": atm_strike,
            "surface_quality": surface_quality,
            "implied_metrics": implied_metrics,
            "best_expiration": best_exp,
            "filter_audit": audit,
        },
        "trace_events": [{
            "node": "volatility_quant_agent",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Selected {best_exp} expiry; Implied Move: {implied_metrics.implied_move_mid_pct*100:.1f}%" if implied_metrics else "No ATM pair found",
        }],
    }


def forecast_node(state: VolAgentState, agent_settings: VolAgentSettings) -> dict[str, Any]:
    """Compute deterministic movement and IV crush forecasts with fail-closed safety."""
    feat_dict = state.get("feature_set", {})
    implied_metrics = feat_dict.get("implied_metrics")
    underlying = state.get("underlying")
    event = state.get("event")
    event_assessment = state.get("event_assessment")

    if implied_metrics is None or underlying is None or event is None:
        # P0-16 Fix: Safe fallback forecast for fail-closed path
        fallback_move = MoveForecast(
            median_abs_move_pct=0.05,
            q20_abs_move_pct=0.02,
            q80_abs_move_pct=0.08,
            implied_move_pct=0.05,
            edge_pct_spot=0.0,
            probability_exceeds_implied=0.50,
            calibration_confidence=0.50,
            out_of_distribution=True,
        )
        fallback_iv = IVCrushForecast(
            median_iv_change_points=-15.0,
            q20_iv_change_points=-25.0,
            q80_iv_change_points=-5.0,
            expected_post_event_atm_iv=0.45,
            calibration_confidence=0.50,
        )
        return {
            "final_decision": Decision.NO_TRADE,
            "abstention_reason": AbstentionReason.DATA_QUALITY,
            "rejection_reasons": ["Missing ATM implied move metrics"],
            "move_forecast": fallback_move,
            "iv_forecast": fallback_iv,
        }

    features = build_quantitative_features(
        underlying=underlying,
        implied_metrics=implied_metrics,
        surface_quality=feat_dict.get("surface_quality", 0.8),
        event=event,
        historical_event_moves=feat_dict.get("historical_moves"),
        event_assessment=event_assessment,
    )

    move_forecast, iv_forecast = compute_shrinkage_forecast(
        features=features,
        historical_ticker_moves=feat_dict.get("historical_moves"),
    )

    return {
        "feature_set": features,
        "move_forecast": move_forecast,
        "iv_forecast": iv_forecast,
        "trace_events": [{
            "node": "forecast_engine",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Forecast median move: {move_forecast.median_abs_move_pct*100:.1f}%, Edge: {move_forecast.edge_pct_spot*100:+.2f}%",
        }],
    }


def long_vol_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Long-Vol Advocate in parallel branch."""
    underlying = state.get("underlying")
    move_fc = state.get("move_forecast")
    iv_fc = state.get("iv_forecast")
    evidence = state.get("evidence", [])

    if not underlying or not move_fc or not iv_fc:
        return {}

    long_thesis = run_long_vol_advocate(underlying.symbol, move_fc, iv_fc, evidence, llm_client=llm_client)

    return {
        "long_vol_thesis": long_thesis,
        "trace_events": [{
            "node": "long_vol_advocate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Long Vol Conf: {long_thesis.confidence*100:.1f}%",
        }],
    }


def short_vol_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Short-Vol Advocate in parallel branch."""
    underlying = state.get("underlying")
    move_fc = state.get("move_forecast")
    iv_fc = state.get("iv_forecast")
    evidence = state.get("evidence", [])

    if not underlying or not move_fc or not iv_fc:
        return {}

    short_thesis = run_short_vol_advocate(underlying.symbol, move_fc, iv_fc, evidence, llm_client=llm_client)

    return {
        "short_vol_thesis": short_thesis,
        "trace_events": [{
            "node": "short_vol_advocate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Short Vol Conf: {short_thesis.confidence*100:.1f}%",
        }],
    }


def critic_and_compliance_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Model-Risk Critic and Track Compliance Guard."""
    underlying = state.get("underlying")
    event = state.get("event")
    chain = state.get("option_chain", [])
    move_fc = state.get("move_forecast")
    evidence = state.get("evidence", [])

    if not underlying or not event or not move_fc:
        from volagent.domain.state import CriticReport
        critic_report = CriticReport(
            status=GateStatus.FAIL,
            directional_leakage_detected=False,
            temporal_leakage_detected=False,
            stale_data_detected=True,
            excessive_model_disagreement=False,
            unsupported_claim_ids=[],
            failure_reasons=["Missing underlying, event, or forecast state in critic"],
            warnings=[],
            recommendation="force_no_trade",
        )
    else:
        critic_report = run_model_risk_critic(
            underlying=underlying,
            event=event,
            option_chain=chain,
            move_forecast=move_fc,
            long_thesis=state.get("long_vol_thesis"),
            short_thesis=state.get("short_vol_thesis"),
            evidence=evidence,
            llm_client=llm_client,
        )

    return {
        "critic_report": critic_report,
        "trace_events": [{
            "node": "model_risk_critic",
            "status": "completed" if critic_report.status == GateStatus.PASS else "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Critic Status: {critic_report.status.value.upper()}, Rec: {critic_report.recommendation}",
        }],
    }


def strategy_and_risk_node(state: VolAgentState, agent_settings: VolAgentSettings) -> dict[str, Any]:
    """Construct strategies, reprice with Monte Carlo, select best, and evaluate Risk Gate."""
    feat = state.get("feature_set", {})
    atm_call = feat.get("atm_call")
    atm_put = feat.get("atm_put")
    implied_metrics = feat.get("implied_metrics")
    underlying = state.get("underlying")
    spot = underlying.price if underlying else 100.0
    chain = state.get("option_chain", [])
    nav = 250_000.0  # $250k portfolio NAV

    candidates = []

    if atm_call and atm_put and "move_forecast" in state and "iv_forecast" in state:
        # 1. Long Straddle
        straddle = build_long_straddle_candidate(atm_call, atm_put, spot, nav, agent_settings.risk)
        straddle = reprice_strategy_monte_carlo(
            straddle, spot, state["move_forecast"], state["iv_forecast"],
            n_scenarios=agent_settings.forecast.monte_carlo_scenarios,
            random_seed=agent_settings.application.random_seed,
            slippage_per_contract=agent_settings.execution.slippage_per_contract,
            fee_per_contract=agent_settings.execution.fee_per_contract,
        )
        candidates.append(straddle)

        # 2. Short Iron Butterfly (if wings available)
        wing_calls = [c for c in chain if c.option_type == "call" and c.strike > atm_call.strike]
        wing_puts = [p for p in chain if p.option_type == "put" and p.strike < atm_put.strike]

        if wing_calls and wing_puts:
            implied_m_d = state["move_forecast"].implied_move_pct * spot
            best_c_wing = min(wing_calls, key=lambda c: abs((c.strike - atm_call.strike) - implied_m_d))
            best_p_wing = min(wing_puts, key=lambda p: abs((atm_put.strike - p.strike) - implied_m_d))

            if best_p_wing.strike < atm_put.strike == atm_call.strike < best_c_wing.strike:
                iron_bfly = build_short_iron_butterfly_candidate(
                    atm_call, atm_put, best_c_wing, best_p_wing, spot, nav, agent_settings.risk
                )
                iron_bfly = reprice_strategy_monte_carlo(
                    iron_bfly, spot, state["move_forecast"], state["iv_forecast"],
                    n_scenarios=agent_settings.forecast.monte_carlo_scenarios,
                    random_seed=agent_settings.application.random_seed,
                    slippage_per_contract=agent_settings.execution.slippage_per_contract,
                    fee_per_contract=agent_settings.execution.fee_per_contract,
                )
                candidates.append(iron_bfly)

    # Strategy Selection with executable ask/bid edges
    critic_report = state.get("critic_report")
    if critic_report and (critic_report.recommendation == "force_no_trade" or critic_report.status == GateStatus.FAIL):
        selected_cand = None
        decision = Decision.NO_TRADE
        abstention = AbstentionReason.CRITIC_VETO
        rejections = list(critic_report.failure_reasons)
    elif "move_forecast" not in state or not candidates:
        selected_cand = None
        decision = Decision.NO_TRADE
        abstention = state.get("abstention_reason", AbstentionReason.DATA_QUALITY)
        rejections = state.get("rejection_reasons", ["No strategy candidates constructed"])
    else:
        selected_cand, decision, abstention, rejections = select_best_strategy(
            candidates=candidates,
            move_forecast=state["move_forecast"],
            implied_metrics=implied_metrics,
            confidence_floor=agent_settings.forecast.confidence_floor,
        )

    # Risk Gate Evaluation
    event = state.get("event")
    move_fc = state.get("move_forecast")

    if event and move_fc:
        risk_report = evaluate_risk_gate(
            candidate=selected_cand,
            decision=decision,
            nav=nav,
            event=event,
            move_forecast=move_fc,
            critic_report=critic_report,
            risk_config=agent_settings.risk,
            spot_price=spot,
            abstention_reason=abstention,
        )
    else:
        from volagent.domain.risk import RiskReport
        risk_report = RiskReport(
            overall_status=GateStatus.FAIL,
            checks=[],
            approved_quantity=0,
            rejection_reasons=["Missing event or forecast for risk evaluation"],
        )

    if risk_report.overall_status == GateStatus.FAIL:
        decision = Decision.NO_TRADE
        abstention = AbstentionReason.RISK_LIMIT
        rejections.extend(risk_report.rejection_reasons)
        approved_cand = None
        audit_proposal = selected_cand
    else:
        approved_cand = selected_cand
        audit_proposal = None

    return {
        "candidates": candidates,
        "approved_candidate": approved_cand,
        "audit_proposal": audit_proposal,
        "final_decision": decision,
        "abstention_reason": abstention,
        "risk_report": risk_report,
        "rejection_reasons": rejections,
        "status": RunStatus.READY_FOR_APPROVAL if decision != Decision.NO_TRADE else RunStatus.COMPLETED,
        "trace_events": [{
            "node": "strategy_and_risk_gate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Final Decision: {decision.value.upper()}, Approved Qty: {risk_report.approved_quantity}",
        }],
    }
