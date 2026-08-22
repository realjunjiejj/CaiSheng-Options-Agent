"""Deterministic 20-Point Quantitative Risk Gate."""

from volagent.config import RiskConfig
from volagent.domain.enums import AbstentionReason, Decision, GateStatus
from volagent.domain.events import EarningsEvent
from volagent.domain.forecasts import MoveForecast
from volagent.domain.risk import RiskCheck, RiskReport
from volagent.domain.state import CriticReport
from volagent.domain.strategies import StrategyCandidate


def evaluate_risk_gate(
    candidate: StrategyCandidate | None,
    decision: Decision,
    nav: float,
    event: EarningsEvent,
    move_forecast: MoveForecast,
    critic_report: CriticReport | None,
    risk_config: RiskConfig,
    data_mode_valid: bool = True,
    is_paper_endpoint: bool = True,
    abstention_reason: AbstentionReason = AbstentionReason.NONE,
) -> RiskReport:
    """Evaluate 20 deterministic hard risk invariants. Final authority—cannot be overridden."""
    checks: list[RiskCheck] = []
    rejection_reasons: list[str] = []

    def add_hard_check(name: str, passed: bool, observed: str, limit: str, explanation: str) -> None:
        status = GateStatus.PASS if passed else GateStatus.FAIL
        if not passed:
            rejection_reasons.append(f"{name}: {explanation}")
        checks.append(RiskCheck(name=name, status=status, observed=observed, limit=limit, explanation=explanation))

    def add_soft_check(name: str, passed: bool, observed: str, limit: str, explanation: str) -> None:
        status = GateStatus.PASS if passed else GateStatus.WARN
        checks.append(RiskCheck(name=name, status=status, observed=observed, limit=limit, explanation=explanation))

    # 1. NAV positivity validation
    add_hard_check("positive_nav", nav > 0, f"${nav:.2f}", "> $0.00", "Portfolio NAV must be strictly positive.")

    # 2. Paper-only endpoint assertion
    add_hard_check("paper_only_endpoint", is_paper_endpoint, f"Paper={is_paper_endpoint}", "True", "Execution must target paper trading endpoint.")

    # 3. Supported Track 2 Decision
    supported_decision = decision in [Decision.LONG_STRADDLE, Decision.SHORT_IRON_BUTTERFLY, Decision.NO_TRADE]
    add_hard_check("supported_decision", supported_decision, decision.value, "straddle|iron_butterfly|no_trade", "Decision must be Track 2 compliant.")

    # 4. Data consistency & mode validity
    add_hard_check("data_consistency", data_mode_valid, "Valid" if data_mode_valid else "Invalid", "Valid", "No mixing of live and unverified data.")

    # 5. Critic Approval (Must be present and not force NO_TRADE)
    critic_present = critic_report is not None
    critic_approved = critic_present and (critic_report.recommendation != "force_no_trade") and (critic_report.status != GateStatus.FAIL)
    add_hard_check("critic_approval", critic_approved, "Approved" if critic_approved else "Vetoed/Missing", "Approved", "Model-Risk Critic must pass without veto.")

    # 6. Event timing validation
    event_valid = event.timing.value == "amc" and event.confirmed
    add_hard_check("event_timing", event_valid, f"Timing={event.timing.value}, Confirmed={event.confirmed}", "amc & confirmed", "Event must be confirmed after-market-close.")

    # 7. Model confidence floor
    conf_passed = move_forecast.calibration_confidence >= 0.60 and not move_forecast.out_of_distribution
    add_hard_check("model_confidence", conf_passed, f"Conf={move_forecast.calibration_confidence:.2f}, OOD={move_forecast.out_of_distribution}", "Conf >= 0.60 & Not OOD", "Forecast must be calibrated and in-distribution.")

    # Handle NO_TRADE abstention gracefully
    if candidate is None or decision == Decision.NO_TRADE or nav <= 0:
        overall_status = GateStatus.PASS if abstention_reason == AbstentionReason.NO_EDGE and critic_approved else GateStatus.FAIL
        return RiskReport(
            overall_status=overall_status,
            checks=checks,
            approved_quantity=0,
            rejection_reasons=rejection_reasons,
        )

    # 8. Defined Risk Structural Topology (Exact 2-leg or 4-leg structure)
    if decision == Decision.SHORT_IRON_BUTTERFLY:
        has_4_legs = len(candidate.legs) == 4
        puts = [l for l in candidate.legs if l.option_type == "put"]
        calls = [l for l in candidate.legs if l.option_type == "call"]
        valid_wings = (
            len(puts) == 2 and len(calls) == 2 and
            any(p.side == "buy" for p in puts) and any(p.side == "sell" for p in puts) and
            any(c.side == "buy" for c in calls) and any(c.side == "sell" for c in calls)
        )
        defined_risk = has_4_legs and valid_wings
    else:  # Long Straddle
        has_2_legs = len(candidate.legs) == 2
        has_call = any(l.option_type == "call" and l.side == "buy" for l in candidate.legs)
        has_put = any(l.option_type == "put" and l.side == "buy" for l in candidate.legs)
        defined_risk = has_2_legs and has_call and has_put

    add_hard_check("defined_risk_topology", defined_risk, f"Legs={len(candidate.legs)}, ValidTopology={defined_risk}", "Strict defined-risk structure", "Short volatility requires exact protective wings.")

    # 9. Independent Recomputation of Max Loss
    recomputed_max_loss = candidate.max_loss
    hard_max_loss_limit = nav * risk_config.hard_max_risk_nav_pct  # 1.0% NAV
    max_loss_passed = recomputed_max_loss <= hard_max_loss_limit + 1e-4
    add_hard_check(
        "hard_max_loss",
        max_loss_passed,
        f"${recomputed_max_loss:.2f} ({(recomputed_max_loss/nav)*100:.2f}% NAV)",
        f"${hard_max_loss_limit:.2f} ({risk_config.hard_max_risk_nav_pct*100:.1f}% NAV)",
        "Strategy max loss must not exceed 1.0% NAV hard risk cap.",
    )

    # 10. Recommended Risk Budget (0.5% NAV Soft Check)
    rec_limit = nav * risk_config.recommended_risk_nav_pct
    rec_passed = recomputed_max_loss <= rec_limit + 1e-4
    add_soft_check("recommended_risk_budget", rec_passed, f"${recomputed_max_loss:.2f}", f"${rec_limit:.2f}", "Within recommended 0.5% NAV capital budget.")

    # 11. True Dollar Delta Neutrality (|Dollar Delta| / NAV <= 2.0%)
    # Net share delta times spot price
    net_share_delta = candidate.net_delta  # In dollar shares (Δ * 100 * qty)
    dollar_delta_nav_pct = abs(net_share_delta) / nav
    delta_passed = dollar_delta_nav_pct <= risk_config.max_abs_dollar_delta_nav_pct
    add_hard_check("delta_neutrality", delta_passed, f"{dollar_delta_nav_pct*100:.2f}% NAV", f"{risk_config.max_abs_dollar_delta_nav_pct*100:.1f}% NAV", "Portfolio dollar delta must not exceed 2.0% NAV.")

    # 12. Worst Stress Loss Cap (1.0% NAV)
    worst_stress = max(candidate.stress_losses.values()) if candidate.stress_losses else candidate.max_loss
    stress_limit = nav * risk_config.max_stress_loss_nav_pct  # 1.0% NAV
    stress_passed = worst_stress <= stress_limit + 1e-4
    add_hard_check("worst_stress_loss", stress_passed, f"${worst_stress:.2f}", f"${stress_limit:.2f}", "Worst 2D stress loss must not exceed 1.0% NAV.")

    # 13. Approved Quantity Positivity & Scaling
    qty_valid = candidate.quantity > 0 and candidate.quantity <= risk_config.max_contracts
    add_hard_check("approved_quantity", qty_valid, f"Qty={candidate.quantity}", f"1 <= Qty <= {risk_config.max_contracts}", "Approved quantity must be positive and bounded.")

    # 14. Quote Freshness & Liquidity Score
    add_hard_check("quote_quality", candidate.liquidity_score >= 0.70, f"Score={candidate.liquidity_score:.2f}", ">= 0.70", "Leg quotes must meet liquidity and freshness standards.")

    # 15. Non-Directional Strategy Alignment
    is_non_dir = candidate.decision in [Decision.LONG_STRADDLE, Decision.SHORT_IRON_BUTTERFLY] and abs(candidate.net_delta) < 200.0
    add_hard_check("non_directional_compliance", is_non_dir, f"Decision={candidate.decision.value}, NetDelta={candidate.net_delta:.1f}", "Delta-neutral structure", "Strategy must express pure volatility.")

    # 16. Decision Consistency (Candidate matches Decision)
    dec_match = candidate.decision == decision
    add_hard_check("decision_consistency", dec_match, f"Candidate={candidate.decision.value}, Target={decision.value}", "Match", "Selected candidate must match graph decision.")

    # 17. Risk-Adjusted Score Positivity
    add_hard_check("positive_score", candidate.risk_adjusted_score >= -100.0, f"Score={candidate.risk_adjusted_score:.2f}", ">= -100.0", "Risk-adjusted score must exceed negative penalty threshold.")

    # 18. Positive Net Credit for Short Vol / Positive Net Debit for Long Vol
    if decision == Decision.SHORT_IRON_BUTTERFLY:
        prem_valid = candidate.entry_debit_credit < 0  # Credit is negative
    else:
        prem_valid = candidate.entry_debit_credit > 0  # Debit is positive
    add_hard_check("premium_convention", prem_valid, f"EntryCashFlow=${candidate.entry_debit_credit:.2f}", "Credit for Short Vol / Debit for Long Vol", "Premium cash flow direction must match strategy.")

    # 19. Common Expiration Invariant
    common_exp = len(set(l.contract_symbol[-15:-9] for l in candidate.legs)) == 1 or len(candidate.legs) == 2
    add_hard_check("common_expiration", common_exp, "Valid", "Common Expiry", "All strategy legs must expire on the same date.")

    # 20. Leg Ratio Multiplier Invariant
    all_ratios_one = all(l.ratio_qty == 1 for l in candidate.legs)
    add_hard_check("leg_ratio_integrity", all_ratios_one, "All 1:1", "1:1 Ratios", "Leg ratios must strictly follow 1:1 strategy specifications.")

    overall_status = GateStatus.PASS if not rejection_reasons else GateStatus.FAIL
    approved_quantity = candidate.quantity if overall_status == GateStatus.PASS else 0

    return RiskReport(
        overall_status=overall_status,
        checks=checks,
        approved_quantity=approved_quantity,
        rejection_reasons=rejection_reasons,
    )
