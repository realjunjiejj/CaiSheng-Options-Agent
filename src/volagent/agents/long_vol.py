"""Long-Vol and Short-Vol Advocates with strict evidence citation integrity and LLM support."""

from typing import Any
from volagent.domain.events import EvidenceItem
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.state import VolatilityThesis


def run_long_vol_advocate(
    symbol: str,
    move_forecast: MoveForecast,
    iv_forecast: IVCrushForecast,
    evidence: list[EvidenceItem],
    llm_client: Any = None,
    *,
    allow_fallback: bool = True,
) -> VolatilityThesis:
    """Argues the Long Volatility thesis (underpriced jump variance). Rejects hallucinated citations."""
    valid_evidence_ids = [e.evidence_id for e in evidence if e.evidence_id]

    if llm_client is not None:
        try:
            prompt_input = (
                f"Symbol: {symbol}\n"
                f"Move Forecast: {move_forecast.model_dump_json()}\n"
                f"IV Forecast: {iv_forecast.model_dump_json()}\n"
                f"Evidence: {[e.model_dump(mode='json') for e in evidence]}"
            )
            structured_llm = llm_client.with_structured_output(VolatilityThesis)
            res = structured_llm.invoke([
                {"role": "system", "content": "You are the Long Volatility Advocate. Argue why options underprice jump variance using delta-neutral long straddles. Strictly cite only provided evidence IDs."},
                {"role": "user", "content": prompt_input},
            ])
            res.supporting_evidence_ids = [eid for eid in res.supporting_evidence_ids if eid in valid_evidence_ids]
            return res
        except Exception:
            if not allow_fallback:
                raise
            pass

    long_edge = move_forecast.edge_pct_spot
    p_exceed = move_forecast.probability_exceeds_implied

    if long_edge > 0:
        thesis = (
            f"Underlying jump variance is underpriced by the options market. "
            f"Forecast median move of {move_forecast.median_abs_move_pct*100:.1f}% exceeds market-implied move "
            f"of {move_forecast.implied_move_pct*100:.1f}% by {long_edge*100:+.2f}%. "
            f"A delta-neutral ATM Long Straddle captures positive gamma (+Γ) while bounding downside risk to entry debit."
        )
        conf = max(0.50, min(0.95, p_exceed))
    else:
        thesis = (
            f"Market is currently pricing an implied move of {move_forecast.implied_move_pct*100:.1f}%, "
            f"which exceeds our forecast median of {move_forecast.median_abs_move_pct*100:.1f}%. "
            f"Long volatility faces negative expected value after friction."
        )
        conf = max(0.10, min(0.49, p_exceed))

    numeric_arg = f"Jump edge: {long_edge*100:+.2f}%, P(Move > Implied): {p_exceed*100:.1f}%"

    return VolatilityThesis(
        side="long_vol",
        directional_view="none",
        thesis=thesis,
        numeric_argument=numeric_arg,
        supporting_evidence_ids=valid_evidence_ids,
        contradicting_evidence_ids=[],
        invalidation_conditions=["Observed realized move compresses below implied move."],
        confidence=round(conf, 2),
        support_score=round(conf, 2),
    )


def run_short_vol_advocate(
    symbol: str,
    move_forecast: MoveForecast,
    iv_forecast: IVCrushForecast,
    evidence: list[EvidenceItem],
    llm_client: Any = None,
    *,
    allow_fallback: bool = True,
) -> VolatilityThesis:
    """Argues the Short Volatility thesis (overpriced IV & IV crush harvest). Rejects hallucinated citations."""
    valid_evidence_ids = [e.evidence_id for e in evidence if e.evidence_id]

    if llm_client is not None:
        try:
            prompt_input = (
                f"Symbol: {symbol}\n"
                f"Move Forecast: {move_forecast.model_dump_json()}\n"
                f"IV Forecast: {iv_forecast.model_dump_json()}\n"
                f"Evidence: {[e.model_dump(mode='json') for e in evidence]}"
            )
            structured_llm = llm_client.with_structured_output(VolatilityThesis)
            res = structured_llm.invoke([
                {"role": "system", "content": "You are the Short Volatility Advocate. Argue why options overprice implied variance using defined-risk short iron butterflies. Strictly cite only provided evidence IDs."},
                {"role": "user", "content": prompt_input},
            ])
            res.supporting_evidence_ids = [eid for eid in res.supporting_evidence_ids if eid in valid_evidence_ids]
            return res
        except Exception:
            if not allow_fallback:
                raise
            pass

    short_edge = -move_forecast.edge_pct_spot
    p_subside = 1.0 - move_forecast.probability_exceeds_implied

    if short_edge > 0:
        thesis = (
            f"Market-implied volatility contains a significant Variance Risk Premium (VRP). "
            f"Market implies a move of {move_forecast.implied_move_pct*100:.1f}%, while historical and forecast jump median "
            f"is only {move_forecast.median_abs_move_pct*100:.1f}%. "
            f"A defined-risk Short Iron Butterfly harvests the {iv_forecast.median_iv_change_points:.1f}-point IV crush "
            f"while long wings strictly limit tail risk."
        )
        conf = max(0.50, min(0.95, p_subside))
    else:
        thesis = (
            f"Market-implied move of {move_forecast.implied_move_pct*100:.1f}% is lower than forecast jump variance of "
            f"{move_forecast.median_abs_move_pct*100:.1f}%. Short volatility carries unacceptable tail risk."
        )
        conf = max(0.10, min(0.49, p_subside))

    numeric_arg = f"VRP Harvest Edge: {short_edge*100:+.2f}%, Expected IV Crush: {iv_forecast.median_iv_change_points:.1f} pts"

    return VolatilityThesis(
        side="short_vol",
        directional_view="none",
        thesis=thesis,
        numeric_argument=numeric_arg,
        supporting_evidence_ids=valid_evidence_ids,
        contradicting_evidence_ids=[],
        invalidation_conditions=["Actual earnings jump exceeds wing boundaries."],
        confidence=round(conf, 2),
        support_score=round(conf, 2),
    )
