"""Deterministic strategy selector based on executable ask/bid edges and risk-adjusted scores."""

from volagent.domain.enums import AbstentionReason, Decision
from volagent.domain.forecasts import MoveForecast
from volagent.domain.strategies import StrategyCandidate
from volagent.quant.expected_move import ImpliedMoveMetrics


def select_best_strategy(
    candidates: list[StrategyCandidate],
    move_forecast: MoveForecast,
    implied_metrics: ImpliedMoveMetrics,
    confidence_floor: float = 0.60,
    require_confidence_bound_edge: bool = False,
    minimum_ev_to_max_loss: float = 0.0,
) -> tuple[StrategyCandidate | None, Decision, AbstentionReason, list[str]]:
    """Select winning strategy candidate using strategy-specific executable edge or enforce NO_TRADE."""
    rejection_reasons: list[str] = []

    # 1. Model Confidence Gate
    if move_forecast.calibration_confidence < confidence_floor:
        rejection_reasons.append(f"Forecast confidence ({move_forecast.calibration_confidence:.2f}) below floor ({confidence_floor:.2f})")
        return None, Decision.NO_TRADE, AbstentionReason.DATA_QUALITY, rejection_reasons

    if move_forecast.out_of_distribution:
        rejection_reasons.append("Forecast feature vector flagged as Out-Of-Distribution (OOD)")
        return None, Decision.NO_TRADE, AbstentionReason.DATA_QUALITY, rejection_reasons

    if not candidates:
        rejection_reasons.append("No viable options strategy candidates could be constructed")
        return None, Decision.NO_TRADE, AbstentionReason.DATA_QUALITY, rejection_reasons

    # 2. Strategy-Specific Executable Edge Bounds
    buf = move_forecast.uncertainty_buffer_pct_spot
    long_edge = move_forecast.median_abs_move_pct - implied_metrics.implied_move_ask_pct
    short_edge = implied_metrics.implied_move_bid_pct - move_forecast.median_abs_move_pct

    target_decision = Decision.NO_TRADE

    if long_edge > buf:
        target_decision = Decision.LONG_STRADDLE
    elif short_edge > buf:
        target_decision = Decision.SHORT_IRON_BUTTERFLY
    else:
        rejection_reasons.append(
            f"Insufficient executable edge: Long edge ({long_edge*100:+.2f}%) and Short edge ({short_edge*100:+.2f}%) "
            f"do not exceed uncertainty buffer (±{buf*100:.2f}%)"
        )
        return None, Decision.NO_TRADE, AbstentionReason.NO_EDGE, rejection_reasons

    if require_confidence_bound_edge:
        long_lower_edge = move_forecast.q20_abs_move_pct - implied_metrics.implied_move_ask_pct
        short_lower_edge = implied_metrics.implied_move_bid_pct - move_forecast.q80_abs_move_pct
        bound_edge = long_lower_edge if target_decision == Decision.LONG_STRADDLE else short_lower_edge
        if bound_edge <= 0.0:
            rejection_reasons.append(
                f"Strategy confidence-bound edge ({bound_edge*100:+.2f}%) is not positive"
            )
            return None, Decision.NO_TRADE, AbstentionReason.NO_EDGE, rejection_reasons

    # Find candidate matching target decision
    matching = [c for c in candidates if c.decision == target_decision and c.quantity > 0]
    if not matching:
        rejection_reasons.append(f"No affordable candidate available matching {target_decision.value}")
        return None, Decision.NO_TRADE, AbstentionReason.RISK_LIMIT, rejection_reasons

    # Pick candidate with highest risk-adjusted score
    matching.sort(key=lambda x: x.risk_adjusted_score, reverse=True)
    best = matching[0]

    ev_to_max_loss = best.expected_pnl / max(best.max_loss, 1e-9)
    if best.expected_pnl <= 0.0 or ev_to_max_loss < minimum_ev_to_max_loss:
        rejection_reasons.append(
            f"Expected P&L ${best.expected_pnl:.2f}; EV/max-loss {ev_to_max_loss:.3f} "
            f"below required {minimum_ev_to_max_loss:.3f}"
        )
        return None, Decision.NO_TRADE, AbstentionReason.NO_EDGE, rejection_reasons

    if best.risk_adjusted_score < -100.0:
        rejection_reasons.append(f"Risk-adjusted score ({best.risk_adjusted_score:.2f}) is negative after tail penalties")
        return None, Decision.NO_TRADE, AbstentionReason.RISK_LIMIT, rejection_reasons

    return best, best.decision, AbstentionReason.NONE, rejection_reasons
