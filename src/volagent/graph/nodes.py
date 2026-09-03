"""LangGraph graph node implementations with strict trust boundaries and fail-closed routing."""

from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any
import uuid

logger = logging.getLogger(__name__)


def _model_identifier(llm_client: Any) -> str | None:
    """Return a non-sensitive model label suitable for immutable receipts."""
    if llm_client is None:
        return None
    for attribute in ("model_name", "model", "model_id"):
        value = getattr(llm_client, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return type(llm_client).__name__


def _agent_runtime_event(
    *,
    name: str,
    mode: str,
    started_at: float,
    llm_client: Any = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Build a sanitized per-role runtime receipt without prompts or responses."""
    return {
        "name": name,
        "runtime_mode": mode,
        "llm_requested": llm_client is not None,
        "model_identifier": _model_identifier(llm_client),
        "latency_ms": max(0, round((time.perf_counter() - started_at) * 1000)),
        "schema_validated": mode in {
            "llm_assisted",
            "deterministic",
            "deterministic_fallback",
        },
        "error_type": error_type,
    }


from volagent.agents.event_magnitude import run_event_magnitude_agent
from volagent.agents.long_vol import run_long_vol_advocate, run_short_vol_advocate
from volagent.agents.model_risk import run_model_risk_critic
from volagent.clock import year_fraction_to_expiry
from volagent.config import VolAgentSettings
from volagent.data.replay import ReplayDataManager
from volagent.domain.enums import AbstentionReason, DataMode, Decision, GateStatus, RunStatus
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.state import VolAgentState
from volagent.quant.expected_move import compute_implied_move
from volagent.quant.features import build_quantitative_features
from volagent.quant.forecast import compute_implied_residual_forecast, compute_shrinkage_forecast
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
    if state.get("underlying") and state.get("event") and state.get("option_chain"):
        evidence = state.get("evidence_items") or state.get("evidence", [])
        return {
            "underlying": state["underlying"],
            "event": state["event"],
            "option_chain": state["option_chain"],
            "evidence": evidence,
            # A supplied historical snapshot must preserve the caller's declared
            # decision boundary.  This prevents the quote filter from comparing
            # every contract to a different underlying-bar timestamp.
            "feature_set": {
                "historical_moves": state.get("historical_moves", []),
                "historical_residuals": state.get("historical_residuals", []),
                "snapshot_time": state["event"].decision_time,
            },
            "artifact_hashes": state.get("artifact_hashes", {}),
            "trace_events": [{
                "node": "fetch_market_snapshot",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": f"Using supplied market snapshot with {len(state['option_chain'])} option quotes",
            }],
        }

    mode = state.get("mode")
    is_live = mode == DataMode.LIVE or getattr(mode, "value", None) == DataMode.LIVE.value
    symbol = str(state.get("symbol") or "").upper()
    if not symbol:
        return {
            "option_chain": [],
            "evidence": [],
            "rejection_reasons": ["A ticker symbol is required; no default underlying is used."],
            "trace_events": [{
                "node": "fetch_market_snapshot",
                "status": "rejected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": "Snapshot rejected: missing ticker symbol.",
            }],
        }

    if is_live:
        from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter

        event = state.get("event")
        now = datetime.now(timezone.utc)
        supported_daily = (
            event is not None
            and event.confirmed
            and event.event_type == "scheduled_volatility"
            and event.timing.value == "dmh"
        )
        supported_event = (
            event is not None
            and event.confirmed
            and event.timing.value == "amc"
        )
        if not (supported_event or supported_daily):
            return {
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": ["Live analysis requires a confirmed AMC event or scheduled daily-volatility opportunity."],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": now.isoformat(), "summary": "Live canary rejected: event is missing, unconfirmed, or not AMC."}],
            }
        invalid_event_window = (
            event.exit_time <= event.decision_time
            or (supported_event and event.event_time <= now)
        )
        if invalid_event_window:
            return {
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": ["Live paper canary requires a future event and a post-event exit time."],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": now.isoformat(), "summary": "Live canary rejected: invalid event window."}],
            }

        adapter = state.get("live_market_adapter") or AlpacaLiveMarketAdapter(
            api_key=agent_settings.alpaca_api_key,
            secret_key=agent_settings.alpaca_secret_key,
            stock_feed=agent_settings.market_data.stock_feed,
            options_feed=agent_settings.market_data.options_feed,
        )
        market_open, _ = adapter.get_market_status()
        if not market_open:
            detail = getattr(adapter, "last_error", None) or "Options market is closed."
            return {
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": [f"Live paper canary blocked: {detail}"],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": now.isoformat(), "summary": "Live canary rejected: market is closed or clock is unavailable."}],
            }

        underlying = adapter.get_underlying_snapshot(symbol)
        if underlying is None:
            return {
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": [f"Live paper canary blocked: {getattr(adapter, 'last_error', None) or 'underlying quote unavailable.'}"],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": now.isoformat(), "summary": "Live canary rejected: no valid underlying quote."}],
            }

        min_expiry = event.event_time.date() + timedelta(days=agent_settings.contracts.min_dte_days)
        max_expiry = event.event_time.date() + timedelta(days=agent_settings.contracts.max_dte_days)
        chain = adapter.get_option_chain(symbol, min_expiry, max_expiry, underlying.price)
        if not chain:
            return {
                "underlying": underlying,
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": [f"Live paper canary blocked: {getattr(adapter, 'last_error', None) or 'no valid option chain.'}"],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": now.isoformat(), "summary": "Live canary rejected: no valid live option contracts."}],
            }

        decision_time = datetime.now(timezone.utc)
        if underlying.quote_time > decision_time:
            return {
                "underlying": underlying,
                "option_chain": [],
                "evidence": [],
                "rejection_reasons": ["Live paper canary blocked: underlying quote timestamp is after decision time."],
                "trace_events": [{"node": "fetch_market_snapshot", "status": "rejected", "timestamp": decision_time.isoformat(), "summary": "Live canary rejected: temporal ordering failure."}],
            }
        live_event = event.model_copy(update={"decision_time": decision_time})
        supplied_history = state.get("historical_moves") or []
        history_dates = state.get("historical_event_dates") or []
        history_reader = getattr(adapter, "get_historical_event_moves", None)
        historical_moves = supplied_history or (
            history_reader(symbol, history_dates, event.event_time.date()) if callable(history_reader) else []
        )
        return {
            "event": live_event,
            "underlying": underlying,
            "option_chain": chain,
            "evidence": state.get("evidence", []),
            "feature_set": {
                "historical_moves": historical_moves,
                "historical_residuals": state.get("historical_residuals", []),
                # Captured after all independently timestamped market-data
                # calls complete; it is the decision boundary for filtering.
                "snapshot_time": decision_time,
            },
            "artifact_hashes": {"live_underlying": underlying.provenance.content_hash, "live_chain_count": str(len(chain))},
            "trace_events": [{"node": "fetch_market_snapshot", "status": "completed", "timestamp": decision_time.isoformat(), "summary": f"Fetched live Alpaca snapshot: {len(chain)} validated option contracts and {len(historical_moves)} verified historical moves for {symbol}."}],
        }

    scenario_id = state.get("scenario_id") or agent_settings.volagent_replay_scenario_id or f"SCENARIO-{symbol}"

    replay_mgr = ReplayDataManager()
    scenario_data = replay_mgr.load_scenario(scenario_id)

    evidence = scenario_data.get("evidence_items") or scenario_data.get("evidence", [])

    return {
        "mode": DataMode.REPLAY_SYNTHETIC,
        "underlying": scenario_data["underlying"],
        "event": scenario_data["event"],
        "option_chain": scenario_data["option_chain"],
        "evidence": evidence,
        "feature_set": {
            "historical_moves": scenario_data.get("historical_moves", []),
            "historical_residuals": scenario_data.get("historical_residuals", []),
        },
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
    started_at = time.perf_counter()
    if not state.get("enable_agent_debate", True):
        return {
            "agent_runtime_events": [_agent_runtime_event(
                name="event_magnitude",
                mode="disabled",
                started_at=started_at,
            )],
            "trace_events": [{
                "node": "event_magnitude_agent",
                "status": "disabled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": "Disabled for quant-only ablation",
            }],
        }

    event = state.get("event")
    evidence = state.get("evidence", [])

    if not event:
        return {}

    runtime_mode = "deterministic"
    error_type = None
    if llm_client is None:
        assessment = run_event_magnitude_agent(event, evidence)
    else:
        try:
            assessment = run_event_magnitude_agent(
                event,
                evidence,
                llm_client=llm_client,
                allow_fallback=False,
            )
            runtime_mode = "llm_assisted"
        except Exception as exc:
            error_type = type(exc).__name__
            runtime_mode = "deterministic_fallback"
            assessment = run_event_magnitude_agent(event, evidence)

    return {
        "event_assessment": assessment,
        "agent_runtime_events": [_agent_runtime_event(
            name="event_magnitude",
            mode=runtime_mode,
            started_at=started_at,
            llm_client=llm_client,
            error_type=error_type,
        )],
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
        as_of_time=state.get("feature_set", {}).get("snapshot_time", underlying.quote_time),
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

    if agent_settings.forecast.model_mode == "implied_residual":
        historical_residuals = feat_dict.get("historical_residuals") or []
        move_forecast, iv_forecast = compute_implied_residual_forecast(
            features=features,
            historical_residuals=historical_residuals,
            residual_shrinkage_weight=agent_settings.forecast.residual_shrinkage_weight,
        )
    else:
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
    started_at = time.perf_counter()
    if not state.get("enable_agent_debate", True):
        return {
            "agent_runtime_events": [_agent_runtime_event(
                name="long_vol_advocate",
                mode="disabled",
                started_at=started_at,
            )],
            "trace_events": [{
                "node": "long_vol_advocate",
                "status": "disabled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": "Disabled for quant-only ablation",
            }],
        }

    underlying = state.get("underlying")
    move_fc = state.get("move_forecast")
    iv_fc = state.get("iv_forecast")
    evidence = state.get("evidence", [])

    if not underlying or not move_fc or not iv_fc:
        return {}

    runtime_mode = "deterministic"
    error_type = None
    call_args = (underlying.symbol, move_fc, iv_fc, evidence)
    if llm_client is None:
        long_thesis = run_long_vol_advocate(*call_args)
    else:
        try:
            long_thesis = run_long_vol_advocate(
                *call_args,
                llm_client=llm_client,
                allow_fallback=False,
            )
            runtime_mode = "llm_assisted"
        except Exception as exc:
            error_type = type(exc).__name__
            runtime_mode = "deterministic_fallback"
            long_thesis = run_long_vol_advocate(*call_args)

    return {
        "long_vol_thesis": long_thesis,
        "agent_runtime_events": [_agent_runtime_event(
            name="long_vol_advocate",
            mode=runtime_mode,
            started_at=started_at,
            llm_client=llm_client,
            error_type=error_type,
        )],
        "trace_events": [{
            "node": "long_vol_advocate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Long Vol Conf: {long_thesis.confidence*100:.1f}%",
        }],
    }


def short_vol_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Short-Vol Advocate in parallel branch."""
    started_at = time.perf_counter()
    if not state.get("enable_agent_debate", True):
        return {
            "agent_runtime_events": [_agent_runtime_event(
                name="short_vol_advocate",
                mode="disabled",
                started_at=started_at,
            )],
            "trace_events": [{
                "node": "short_vol_advocate",
                "status": "disabled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": "Disabled for quant-only ablation",
            }],
        }

    underlying = state.get("underlying")
    move_fc = state.get("move_forecast")
    iv_fc = state.get("iv_forecast")
    evidence = state.get("evidence", [])

    if not underlying or not move_fc or not iv_fc:
        return {}

    runtime_mode = "deterministic"
    error_type = None
    call_args = (underlying.symbol, move_fc, iv_fc, evidence)
    if llm_client is None:
        short_thesis = run_short_vol_advocate(*call_args)
    else:
        try:
            short_thesis = run_short_vol_advocate(
                *call_args,
                llm_client=llm_client,
                allow_fallback=False,
            )
            runtime_mode = "llm_assisted"
        except Exception as exc:
            error_type = type(exc).__name__
            runtime_mode = "deterministic_fallback"
            short_thesis = run_short_vol_advocate(*call_args)

    return {
        "short_vol_thesis": short_thesis,
        "agent_runtime_events": [_agent_runtime_event(
            name="short_vol_advocate",
            mode=runtime_mode,
            started_at=started_at,
            llm_client=llm_client,
            error_type=error_type,
        )],
        "trace_events": [{
            "node": "short_vol_advocate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Short Vol Conf: {short_thesis.confidence*100:.1f}%",
        }],
    }


def critic_and_compliance_node(state: VolAgentState, agent_settings: VolAgentSettings, llm_client: Any = None) -> dict[str, Any]:
    """Run Model-Risk Critic and Track Compliance Guard."""
    started_at = time.perf_counter()
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
            require_advocates=state.get("enable_agent_debate", True),
        )

    return {
        "critic_report": critic_report,
        "agent_runtime_events": [_agent_runtime_event(
            name="model_risk_critic",
            mode="deterministic",
            started_at=started_at,
        )],
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
    nav = float(state.get("nav", 100_000.0))
    risk_config = agent_settings.risk.model_copy(update={"max_contracts": 1}) if state.get("paper_canary", False) else agent_settings.risk
    event = state.get("event")

    def remaining_time_at_exit(candidate: Any) -> float:
        """Calculate option time remaining at the declared strategy exit."""
        if event is None or not candidate.legs:
            return 1.0 / 365.0
        return max(
            1.0 / 365.0,
            min(year_fraction_to_expiry(event.exit_time, leg.expiration) for leg in candidate.legs),
        )

    candidates = []

    if atm_call and atm_put and "move_forecast" in state and "iv_forecast" in state:
        # 1. Long Straddle
        straddle = build_long_straddle_candidate(atm_call, atm_put, spot, nav, risk_config)
        straddle = reprice_strategy_monte_carlo(
            straddle, spot, state["move_forecast"], state["iv_forecast"],
            n_scenarios=agent_settings.forecast.monte_carlo_scenarios,
            random_seed=agent_settings.application.random_seed,
            exit_horizon_years=remaining_time_at_exit(straddle),
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
                    atm_call, atm_put, best_c_wing, best_p_wing, spot, nav, risk_config
                )
                iron_bfly = reprice_strategy_monte_carlo(
                    iron_bfly, spot, state["move_forecast"], state["iv_forecast"],
                    n_scenarios=agent_settings.forecast.monte_carlo_scenarios,
                    random_seed=agent_settings.application.random_seed,
                    exit_horizon_years=remaining_time_at_exit(iron_bfly),
                    slippage_per_contract=agent_settings.execution.slippage_per_contract,
                    fee_per_contract=agent_settings.execution.fee_per_contract,
                )
                candidates.append(iron_bfly)

    # OOD (Out-of-Distribution) Evaluation
    from volagent.quant.ood import detect_out_of_distribution
    move_fc = state.get("move_forecast")
    atm_iv_val = getattr(implied_metrics, "straddle_iv_avg", 0.45) if implied_metrics else 0.45
    ood_result = detect_out_of_distribution(
        spot=spot,
        atm_iv=atm_iv_val,
        implied_move_pct=(implied_metrics.implied_move_ask_pct if implied_metrics else 0.05),
        expected_move_median_pct=(move_fc.median_abs_move_pct if move_fc else 0.05),
        atm_bid=(getattr(atm_call, "bid", 0.0) if atm_call else 0.0),
        atm_ask=(getattr(atm_call, "ask", 0.0) if atm_call else 0.0),
    )
    is_ood = ood_result.is_out_of_distribution

    # Strategy Selection with executable ask/bid edges
    critic_report = state.get("critic_report")
    if is_ood:
        selected_cand = None
        decision = Decision.NO_TRADE
        abstention = AbstentionReason.DATA_QUALITY
        rejections = list(ood_result.reasons)

    elif critic_report and (critic_report.recommendation == "force_no_trade" or critic_report.status == GateStatus.FAIL):
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
            require_confidence_bound_edge=agent_settings.forecast.require_confidence_bound_edge,
            minimum_ev_to_max_loss=agent_settings.forecast.minimum_ev_to_max_loss,
        )

    # Risk Gate & Portfolio Gate Evaluation
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
            risk_config=risk_config,
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

    # Evaluate Portfolio Mandate Gate if candidate is selected
    from volagent.quant.portfolio_gate import evaluate_portfolio_gate
    from volagent.domain.portfolio import PortfolioSnapshot
    from volagent.execution.ledger import ExecutionLedger

    ledger = state.get("ledger") or ExecutionLedger()
    portfolio_snap = state.get("portfolio_snapshot") or PortfolioSnapshot(
        equity=nav,
        cash=nav,
        buying_power=nav * 2.0,
        initial_nav=100000.0,
        high_water_equity=max(100000.0, nav),
        timestamp=datetime.now(timezone.utc),
    )

    port_gate = evaluate_portfolio_gate(
        candidate=selected_cand,
        decision=decision,
        portfolio=portfolio_snap,
        mandate_config=agent_settings.mandate,
        underlying_symbol=underlying.symbol if underlying else "NVDA",
        is_paper_endpoint=True,
        ledger=ledger,
        is_close_order=False,
    )


    governor_enabled = state.get("enable_risk_governor", True)
    governor_bypassed = (
        not governor_enabled
        and (risk_report.overall_status == GateStatus.FAIL or port_gate.overall_status == GateStatus.FAIL)
        and selected_cand is not None
        and decision != Decision.NO_TRADE
    )

    if (risk_report.overall_status == GateStatus.FAIL or port_gate.overall_status == GateStatus.FAIL) and governor_enabled:
        decision = Decision.NO_TRADE
        abstention = AbstentionReason.RISK_LIMIT
        rejections.extend(risk_report.rejection_reasons)
        rejections.extend(port_gate.rejection_reasons)
        approved_cand = None
        audit_proposal = selected_cand
    else:
        approved_cand = selected_cand
        audit_proposal = None

    # Construct authoritative DecisionRecord (caisheng.decision.v1)
    from volagent.domain.decision_record import (
        AgentComponentRuntime,
        AgentRuntimeSummary,
        CriticSummary,
        DecisionRecord,
        RiskSummary,
        SnapshotMetadata,
        StrategyProposal,
        VolatilityView,
    )

    sym = underlying.symbol if underlying else "UNKNOWN"
    now_utc = datetime.now(timezone.utc)
    ev_dt_str = event.event_time.isoformat() if event and hasattr(event.event_time, "isoformat") else str(now_utc.isoformat())
    ev_url = (
        getattr(event, "source_url", None)
        or (event.provenance.source_uri if event and hasattr(event, "provenance") and hasattr(event.provenance, "source_uri") else None)
        or "https://ir.sec.gov"
    )
    ev_id = event.event_id if event else f"evt-{now_utc.strftime('%Y%m%d')}-{sym}"

    data_mode_label = state.get("mode") or state.get("data_mode", "live_read_only")
    if hasattr(data_mode_label, "value"):
        data_mode_label = data_mode_label.value
    is_replay = str(data_mode_label).startswith("replay")
    option_quote_times = [
        contract.quote_time
        for contract in chain
        if getattr(contract, "quote_time", None) is not None
    ]
    option_snapshot_time = max(option_quote_times) if option_quote_times else (
        underlying.quote_time if underlying else now_utc
    )
    stock_feed = "replay_synthetic" if is_replay else (
        getattr(underlying, "data_feed", None) or agent_settings.market_data.stock_feed
    )
    option_feeds = {
        str(getattr(contract, "data_feed", "unknown"))
        for contract in chain
        if getattr(contract, "data_feed", "unknown") != "unknown"
    }
    if is_replay:
        options_feed = "replay_synthetic"
    elif len(option_feeds) == 1:
        options_feed = next(iter(option_feeds))
    elif option_feeds:
        options_feed = "mixed"
    else:
        options_feed = agent_settings.market_data.options_feed

    snap_meta = SnapshotMetadata(
        symbol=sym,
        spot=spot,
        underlying_quote_time=underlying.quote_time.isoformat() if underlying and hasattr(underlying.quote_time, "isoformat") else str(now_utc.isoformat()),
        option_snapshot_time=option_snapshot_time.isoformat(),
        event_id=ev_id,
        event_time=ev_dt_str,
        event_source_url=ev_url,
        stock_feed=stock_feed,
        options_feed=options_feed,
        options_feed_is_indicative=options_feed == "indicative",
    )

    vol_view = VolatilityView(
        implied_move_bid_pct=implied_metrics.implied_move_bid_pct if implied_metrics else 0.04,
        implied_move_ask_pct=implied_metrics.implied_move_ask_pct if implied_metrics else 0.05,
        expected_move_median_pct=move_fc.median_abs_move_pct if move_fc else 0.05,
        q20_pct=move_fc.q20_abs_move_pct if move_fc else 0.02,
        q80_pct=move_fc.q80_abs_move_pct if move_fc else 0.08,
        expected_iv_crush_points=state.get("iv_forecast").median_iv_change_points if state.get("iv_forecast") else -15.0,
        forecast_confidence=move_fc.calibration_confidence if move_fc else 0.50,
        out_of_distribution=is_ood or (move_fc.out_of_distribution if move_fc else False),
    )

    strategy_proposals = []
    for cand in candidates:
        cand_edge = (move_fc.median_abs_move_pct - implied_metrics.implied_move_ask_pct) if (cand.decision == Decision.LONG_STRADDLE and implied_metrics and move_fc) else 0.0
        if cand.decision == Decision.SHORT_IRON_BUTTERFLY and implied_metrics and move_fc:
            cand_edge = implied_metrics.implied_move_bid_pct - move_fc.median_abs_move_pct
        strategy_proposals.append(
            StrategyProposal(
                strategy=cand.decision.name,
                executable_edge_pct=round(cand_edge, 4),
                expected_pnl_dollars=round(cand.expected_pnl, 2),
                max_loss_dollars=round(cand.max_loss, 2),
                risk_adjusted_score=round(cand.risk_adjusted_score, 2),
                rejection_reasons=rejections if cand != approved_cand else [],
            )
        )

    risk_sum = RiskSummary(
        mandate_version="caisheng-mandate-v1",
        current_equity=nav,
        reserved_risk_before=portfolio_snap.reserved_risk_dollars,
        reserved_risk_after=portfolio_snap.reserved_risk_dollars + (approved_cand.max_loss if approved_cand else 0.0),
        hard_checks=[f"{c.name}: {c.status.value.upper()}" for c in (risk_report.checks + port_gate.checks)],
        warnings=getattr(risk_report, "warnings", []),
        rejection_reasons=rejections,
    )

    crit_sum = CriticSummary(
        recommendation=critic_report.recommendation if critic_report else "continue",
        warnings=critic_report.warnings if critic_report else [],
        failure_reasons=critic_report.failure_reasons if critic_report else [],
    )

    dec_status = "APPROVED" if (approved_cand and decision != Decision.NO_TRADE) else "NO_TRADE"

    runtime_components = [
        AgentComponentRuntime.model_validate(event)
        for event in state.get("agent_runtime_events", [])
    ]
    llm_succeeded = sorted(
        component.name
        for component in runtime_components
        if component.runtime_mode == "llm_assisted"
    )
    fallback_nodes = sorted(
        component.name
        for component in runtime_components
        if component.runtime_mode == "deterministic_fallback"
    )
    if fallback_nodes and llm_succeeded:
        runtime_mode = "mixed_fallback"
    elif fallback_nodes:
        runtime_mode = "deterministic_fallback"
    elif llm_succeeded:
        runtime_mode = "llm_assisted"
    else:
        runtime_mode = "deterministic"
    model_identifiers = sorted({
        component.model_identifier
        for component in runtime_components
        if component.model_identifier
    })
    agent_runtime = AgentRuntimeSummary(
        mode=runtime_mode,
        llm_requested=any(component.llm_requested for component in runtime_components),
        model_identifier=", ".join(model_identifiers) if model_identifiers else None,
        llm_nodes_succeeded=llm_succeeded,
        fallback_nodes=fallback_nodes,
        components=runtime_components,
    )

    unique_dec_id = f"dec-{now_utc.strftime('%Y%m%d-%H%M%S')}-{sym}-{uuid.uuid4().hex[:6]}"
    decision_rec = DecisionRecord.create_and_hash(
        decision_id=unique_dec_id,
        run_id=state.get("run_id", "run-default"),
        strategy_version="caisheng-1.0.0",
        mode=data_mode_label,
        status=dec_status,
        generated_at=now_utc.isoformat(),
        snapshot=snap_meta,
        volatility_view=vol_view,
        proposals=strategy_proposals,
        selected_action=decision.name,
        selected_strategy_id=approved_cand.strategy_id if approved_cand else None,
        quantity=risk_report.approved_quantity,
        risk=risk_sum,
        critic=crit_sum,
        agent_runtime=agent_runtime,
    )

    # Persist decision record into SQLite ledger
    try:
        ledger.record_decision_record(decision_rec)
    except Exception as exc:
        logger.error(f"Failed to persist decision record: {exc}")
        raise ExecutionError(f"DecisionRecord persistence failed: {exc}") from exc



    return {
        "candidates": candidates,
        "approved_candidate": approved_cand,
        "audit_proposal": audit_proposal,
        "final_decision": decision,
        "abstention_reason": abstention,
        "risk_report": risk_report,
        "decision_record": decision_rec,
        "governor_bypassed": governor_bypassed,
        "rejection_reasons": rejections,
        "status": RunStatus.READY_FOR_APPROVAL if decision != Decision.NO_TRADE else RunStatus.COMPLETED,
        "trace_events": [{
            "node": "strategy_and_risk_gate",
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Final Decision: {decision.value.upper()}, Approved Qty: {risk_report.approved_quantity}",
        }],
    }
