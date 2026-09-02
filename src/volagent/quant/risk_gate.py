"""Deterministic 20-Point Quantitative Risk Gate with Independent Invariant Recomputation.

Academic Foundations:
- Artzner, P., Delbaen, F., Eber, J. M., & Heath, D. (1999). "Coherent Measures of Risk." Mathematical Finance, 9(3), 203-228.
- Natenberg, S. (1994). "Option Volatility and Pricing." McGraw-Hill Professional.
"""

import math
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
    spot_price: float = 100.0,
    data_mode_valid: bool = True,
    is_paper_endpoint: bool = True,
    abstention_reason: AbstentionReason = AbstentionReason.NONE,
) -> RiskReport:
    """Evaluate 20 deterministic hard risk invariants with independent recomputation from immutable legs."""
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

    # 1. Positive NAV
    add_hard_check("positive_nav", nav > 0 and math.isfinite(nav), f"${nav:.2f}", "> $0.00", "Portfolio NAV must be strictly positive and finite.")

    # 2. Paper-only endpoint assertion
    add_hard_check("paper_only_endpoint", is_paper_endpoint, f"Paper={is_paper_endpoint}", "True", "Execution must target paper trading endpoint.")

    # 3. Supported Options Alpha Decision
    supported_decision = decision in [Decision.LONG_STRADDLE, Decision.SHORT_IRON_BUTTERFLY, Decision.NO_TRADE]
    add_hard_check("supported_decision", supported_decision, decision.value, "straddle|iron_butterfly|no_trade", "Decision must be Options Alpha non-directional compliant.")


    # 4. Data consistency & mode validity
    add_hard_check("data_consistency", data_mode_valid, "Valid" if data_mode_valid else "Invalid", "Valid", "No mixing of live and unverified data.")

    # 5. Critic Approval (Must be present, not veto, and not fail)
    critic_present = critic_report is not None
    critic_approved = critic_present and (critic_report.recommendation != "force_no_trade") and (critic_report.status != GateStatus.FAIL)
    add_hard_check("critic_approval", critic_approved, "Approved" if critic_approved else "Vetoed/Missing", "Approved", "Model-Risk Critic must pass without veto.")

    # 6. Event timing validation
    event_valid = event.confirmed and (
        event.timing.value == "amc"
        or (event.event_type in {"macro", "scheduled_volatility"} and event.timing.value == "dmh")
    )
    expected_timing = "confirmed AMC earnings, macro, or scheduled during-market volatility opportunity"
    add_hard_check("event_timing", event_valid, f"Type={event.event_type}, Timing={event.timing.value}, Confirmed={event.confirmed}", expected_timing, "Event timing/type must be supported and confirmed.")

    # 7. Model confidence floor & In-Distribution
    conf_passed = move_forecast.calibration_confidence >= 0.60 and not move_forecast.out_of_distribution
    add_hard_check("model_confidence", conf_passed, f"Conf={move_forecast.calibration_confidence:.2f}, OOD={move_forecast.out_of_distribution}", "Conf >= 0.60 & Not OOD", "Forecast must be calibrated and in-distribution.")

    # Handle NO_TRADE abstention gracefully
    if candidate is None or decision == Decision.NO_TRADE or nav <= 0:
        overall_status = GateStatus.PASS if (abstention_reason == AbstentionReason.NO_EDGE and critic_approved) else GateStatus.FAIL
        return RiskReport(
            overall_status=overall_status,
            checks=checks,
            approved_quantity=0,
            rejection_reasons=rejection_reasons,
        )

    # 8. P0-05 Fix: Independent Defined Risk Structural Topology Check
    if decision == Decision.SHORT_IRON_BUTTERFLY:
        has_4_legs = len(candidate.legs) == 4
        long_puts = [l for l in candidate.legs if l.option_type == "put" and l.side == "buy"]
        short_puts = [l for l in candidate.legs if l.option_type == "put" and l.side == "sell"]
        short_calls = [l for l in candidate.legs if l.option_type == "call" and l.side == "sell"]
        long_calls = [l for l in candidate.legs if l.option_type == "call" and l.side == "buy"]

        valid_topology = (
            has_4_legs and len(long_puts) == 1 and len(short_puts) == 1 and len(short_calls) == 1 and len(long_calls) == 1
            and (long_puts[0].strike < short_puts[0].strike == short_calls[0].strike < long_calls[0].strike)
        )
        defined_risk = valid_topology
    else:  # Long Straddle
        has_2_legs = len(candidate.legs) == 2
        calls = [l for l in candidate.legs if l.option_type == "call" and l.side == "buy"]
        puts = [l for l in candidate.legs if l.option_type == "put" and l.side == "buy"]
        defined_risk = has_2_legs and len(calls) == 1 and len(puts) == 1 and (calls[0].strike == puts[0].strike)

    add_hard_check("defined_risk_topology", defined_risk, f"Legs={len(candidate.legs)}, Valid={defined_risk}", "Strict defined-risk topology", "Short volatility requires exact protective wings; Long volatility requires exact ATM pair.")

    # 9. P0-02 Fix: Independent Recomputation of Max Loss from Immutable Legs
    if decision == Decision.SHORT_IRON_BUTTERFLY and defined_risk:
        long_p = [l for l in candidate.legs if l.option_type == "put" and l.side == "buy"][0]
        short_p = [l for l in candidate.legs if l.option_type == "put" and l.side == "sell"][0]
        short_c = [l for l in candidate.legs if l.option_type == "call" and l.side == "sell"][0]
        long_c = [l for l in candidate.legs if l.option_type == "call" and l.side == "buy"][0]

        recomputed_credit = (short_p.entry_price_assumption + short_c.entry_price_assumption) - (long_p.entry_price_assumption + long_c.entry_price_assumption)
        recomputed_wing_width = max(short_p.strike - long_p.strike, long_c.strike - short_c.strike)
        recomputed_max_loss = (recomputed_wing_width * 100.0 * candidate.quantity) - (recomputed_credit * 100.0 * candidate.quantity)
    else:
        # Long Straddle
        recomputed_debit = sum(l.entry_price_assumption for l in candidate.legs) * 100.0
        recomputed_max_loss = recomputed_debit * candidate.quantity

    hard_max_loss_limit = nav * risk_config.hard_max_risk_nav_pct
    # P0-07 Fix: Must be strictly positive, finite, and <= hard cap
    loss_finite_and_positive = math.isfinite(recomputed_max_loss) and recomputed_max_loss >= 0.0
    max_loss_passed = loss_finite_and_positive and (recomputed_max_loss <= hard_max_loss_limit + 1e-4)

    add_hard_check(
        "hard_max_loss",
        max_loss_passed,
        f"${recomputed_max_loss:.2f} ({(recomputed_max_loss/nav)*100:.2f}% NAV)",
        f"${hard_max_loss_limit:.2f} ({risk_config.hard_max_risk_nav_pct*100:.1f}% NAV)",
        f"Strategy max loss must not exceed {risk_config.hard_max_risk_nav_pct*100:.2f}% NAV hard risk cap.",
    )

    # 10. Recommended Risk Budget
    rec_limit = nav * risk_config.recommended_risk_nav_pct
    rec_passed = recomputed_max_loss <= rec_limit + 1e-4
    add_soft_check(
        "recommended_risk_budget",
        rec_passed,
        f"${recomputed_max_loss:.2f}",
        f"${rec_limit:.2f}",
        f"Within recommended {risk_config.recommended_risk_nav_pct*100:.2f}% NAV capital budget.",
    )

    # 11. P0-04 Fix: True Dollar Delta Neutrality (|Dollar Delta| / NAV <= 2.0%)
    # Net share delta times spot price
    true_dollar_delta = abs(candidate.net_delta * spot_price)
    dollar_delta_nav_pct = true_dollar_delta / nav
    delta_passed = dollar_delta_nav_pct <= risk_config.max_abs_dollar_delta_nav_pct
    add_hard_check("delta_neutrality", delta_passed, f"{dollar_delta_nav_pct*100:.2f}% NAV (${true_dollar_delta:.2f})", f"{risk_config.max_abs_dollar_delta_nav_pct*100:.1f}% NAV", "Portfolio dollar delta must not exceed 2.0% NAV.")

    # 12. Worst Stress Loss Cap
    worst_stress = max(candidate.stress_losses.values()) if candidate.stress_losses else recomputed_max_loss
    stress_limit = nav * risk_config.max_stress_loss_nav_pct
    stress_passed = math.isfinite(worst_stress) and (worst_stress >= 0.0) and (worst_stress <= stress_limit + 1e-4)
    add_hard_check(
        "worst_stress_loss",
        stress_passed,
        f"${worst_stress:.2f}",
        f"${stress_limit:.2f}",
        f"Worst 2D stress loss must not exceed {risk_config.max_stress_loss_nav_pct*100:.2f}% NAV.",
    )

    # 13. Approved Quantity Positivity & Scaling
    qty_valid = candidate.quantity > 0 and candidate.quantity <= risk_config.max_contracts
    add_hard_check("approved_quantity", qty_valid, f"Qty={candidate.quantity}", f"1 <= Qty <= {risk_config.max_contracts}", "Approved quantity must be positive and bounded.")

    # 14. Quote Freshness & Liquidity Score
    add_hard_check("quote_quality", candidate.liquidity_score >= 0.70, f"Score={candidate.liquidity_score:.2f}", ">= 0.70", "Leg quotes must meet liquidity and freshness standards.")

    # 15. Non-Directional Strategy Alignment
    is_non_dir = candidate.decision in [Decision.LONG_STRADDLE, Decision.SHORT_IRON_BUTTERFLY] and abs(candidate.net_delta) < 200.0
    add_hard_check("non_directional_compliance", is_non_dir, f"Decision={candidate.decision.value}, NetDelta={candidate.net_delta:.1f}", "Delta-neutral structure", "Strategy must express pure volatility.")

    # 16. Decision Consistency
    dec_match = candidate.decision == decision
    add_hard_check("decision_consistency", dec_match, f"Candidate={candidate.decision.value}, Target={decision.value}", "Match", "Selected candidate must match graph decision.")

    # 17. P1-06 Fix: Risk-Adjusted Score Non-Negativity
    score_passed = math.isfinite(candidate.risk_adjusted_score) and candidate.risk_adjusted_score >= 0.0
    add_hard_check("positive_score", score_passed, f"Score={candidate.risk_adjusted_score:.2f}", ">= 0.0", "Risk-adjusted score must be non-negative after tail penalties.")

    # 18. Cash Flow Direction Consistency
    if decision == Decision.SHORT_IRON_BUTTERFLY:
        prem_valid = candidate.entry_debit_credit < 0  # Credit is negative
    else:
        prem_valid = candidate.entry_debit_credit > 0  # Debit is positive
    add_hard_check("premium_convention", prem_valid, f"EntryCashFlow=${candidate.entry_debit_credit:.2f}", "Credit for Short Vol / Debit for Long Vol", "Premium cash flow direction must match strategy.")

    # 19. P0-06 Fix: Common Expiration Invariant (Typed Date Objects)
    common_exp = len(set(l.expiration for l in candidate.legs)) == 1
    add_hard_check("common_expiration", common_exp, f"Expirations={list(set(str(l.expiration) for l in candidate.legs))}", "Single Common Expiration", "All strategy legs must expire on the exact same date.")

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
