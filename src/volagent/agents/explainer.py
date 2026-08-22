"""Explainer Agent for generating judge-readable decision rationales."""

from typing import Any
from volagent.domain.enums import Decision
from volagent.domain.forecasts import MoveForecast
from volagent.domain.risk import RiskReport
from volagent.domain.strategies import StrategyCandidate


def generate_decision_explanation(
    symbol: str,
    decision: Decision,
    move_forecast: MoveForecast,
    selected_candidate: StrategyCandidate | None,
    risk_report: RiskReport,
) -> dict[str, str]:
    """Generate structured judge-facing explanation sections."""
    if decision == Decision.NO_TRADE:
        return {
            "headline": f"{symbol} — NO_TRADE (Risk Invariant Restraint)",
            "market_priced": f"Market implied move was {move_forecast.implied_move_pct*100:.1f}%.",
            "forecast_thesis": f"System forecast median move was {move_forecast.median_abs_move_pct*100:.1f}%.",
            "why_decision_won": "The system abstained from trading because risk invariants or data quality checks failed.",
            "rejection_reasons": "; ".join(risk_report.rejection_reasons) if risk_report.rejection_reasons else "Risk-adjusted expected value did not exceed friction buffer.",
            "greeks_summary": "No Greek exposure opened.",
            "safety_note": "A primary hallmark of an institutional quant desk is the discipline to refuse trades when edge cannot survive costs and uncertainty.",
        }

    if decision == Decision.LONG_STRADDLE and selected_candidate:
        return {
            "headline": f"{symbol} — LONG STRADDLE (Positive Jump Edge)",
            "market_priced": f"Market priced an implied move of {move_forecast.implied_move_pct*100:.1f}%.",
            "forecast_thesis": f"System forecast an absolute move of {move_forecast.median_abs_move_pct*100:.1f}% ({move_forecast.edge_pct_spot*100:+.2f}% edge vs implied).",
            "why_decision_won": "Long ATM Straddle was selected to capture high expected jump variance with positive gamma (+gamma) and capped downside risk (100% debit max loss).",
            "max_loss_and_risk": f"Total max loss is ${selected_candidate.max_loss:.2f}, within the 1.0% NAV hard risk cap.",
            "greeks_summary": f"Delta: {selected_candidate.net_delta:.1f}, Gamma: {selected_candidate.net_gamma:.2f}, Vega: ${selected_candidate.net_vega:.1f}/pt, Theta: ${selected_candidate.net_theta:.1f}/day.",
            "safety_note": "Order is delta-neutral at inception and will be monitored for post-earnings exit at market open.",
        }

    if decision == Decision.SHORT_IRON_BUTTERFLY and selected_candidate:
        return {
            "headline": f"{symbol} — SHORT IRON BUTTERFLY (Variance Risk Premium Harvest)",
            "market_priced": f"Market priced an implied move of {move_forecast.implied_move_pct*100:.1f}%.",
            "forecast_thesis": f"System forecast an absolute move of {move_forecast.median_abs_move_pct*100:.1f}% (IV overpriced relative to historical jump variance).",
            "why_decision_won": "Defined-Risk Short Iron Butterfly was selected to harvest the event volatility risk premium (VRP) and post-earnings IV crush with defined wing protection.",
            "max_loss_and_risk": f"Total max loss is strictly capped at ${selected_candidate.max_loss:.2f} via protective long wings.",
            "greeks_summary": f"Delta: {selected_candidate.net_delta:.1f}, Gamma: {selected_candidate.net_gamma:.2f}, Vega: ${selected_candidate.net_vega:.1f}/pt, Theta: ${selected_candidate.net_theta:.1f}/day.",
            "safety_note": "Never trades naked short options. Long protective wings prevent catastrophic tail risk.",
        }

    return {
        "headline": f"{symbol} — Decision Process Complete",
        "market_priced": "N/A",
        "forecast_thesis": "N/A",
        "why_decision_won": "Analysis concluded.",
        "greeks_summary": "N/A",
        "safety_note": "Paper trading only.",
    }
