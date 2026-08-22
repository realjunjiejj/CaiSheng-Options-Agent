"""Model-Risk Critic and Track Compliance Guard."""

from datetime import datetime, timezone
from typing import Any

from volagent.domain.enums import GateStatus
from volagent.domain.events import EarningsEvent
from volagent.domain.forecasts import MoveForecast
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.state import CriticReport, VolatilityThesis

FORBIDDEN_DIRECTIONAL_TERMS = [
    "bullish",
    "bearish",
    "buy calls",
    "buy puts",
    "stock will go up",
    "stock will go down",
    "directional long",
    "directional short",
]


def validate_track_compliance(
    long_thesis: VolatilityThesis | None,
    short_thesis: VolatilityThesis | None,
    extra_texts: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Strictly audit agent texts to prevent directional bias."""
    violations = []
    texts_to_check = []

    if long_thesis:
        if long_thesis.directional_view != "none":
            violations.append(f"Long-Vol Advocate leaked directional view: {long_thesis.directional_view}")
        texts_to_check.append(long_thesis.thesis.lower())

    if short_thesis:
        if short_thesis.directional_view != "none":
            violations.append(f"Short-Vol Advocate leaked directional view: {short_thesis.directional_view}")
        texts_to_check.append(short_thesis.thesis.lower())

    for txt in extra_texts or []:
        texts_to_check.append(txt.lower())

    for t in texts_to_check:
        for term in FORBIDDEN_DIRECTIONAL_TERMS:
            if term in t:
                violations.append(f"Forbidden directional term detected: '{term}'")

    return (len(violations) == 0), violations


def run_model_risk_critic(
    underlying: UnderlyingSnapshot,
    event: EarningsEvent,
    option_chain: list[OptionContractSnapshot],
    move_forecast: MoveForecast,
    long_thesis: VolatilityThesis | None = None,
    short_thesis: VolatilityThesis | None = None,
    llm_client: Any = None,
) -> CriticReport:
    """Independent risk and compliance audit. Can force NO_TRADE."""
    failure_reasons = []
    warnings = []

    # 1. Stale quote audit: check quote age against decision time
    age_seconds = (event.decision_time - underlying.quote_time).total_seconds()
    stale_data = age_seconds > 1800 or age_seconds < 0

    if stale_data:
        failure_reasons.append(f"Stale or invalid market quotes (Age: {age_seconds/60:.1f} minutes).")

    # 2. Temporal leakage: ensure quote time is prior to event time
    temporal_leakage = (underlying.quote_time > event.event_time) or any(c.quote_time > event.event_time for c in option_chain)
    if temporal_leakage:
        failure_reasons.append("Temporal leakage detected: Market quotes observed after event start time.")

    # 3. Chain Liquidity audit
    if len(option_chain) < 2:
        failure_reasons.append("Insufficient liquid options chain available for strategy construction.")

    # 4. Out-of-Distribution audit
    if move_forecast.out_of_distribution:
        failure_reasons.append("Quantitative forecast feature vector flagged as Out-Of-Distribution.")

    # 5. Track 02 Compliance Audit
    compliant, dir_violations = validate_track_compliance(long_thesis, short_thesis)
    if not compliant:
        failure_reasons.extend(dir_violations)

    status = GateStatus.FAIL if failure_reasons else GateStatus.PASS
    rec = "force_no_trade" if failure_reasons else "continue"

    return CriticReport(
        status=status,
        directional_leakage_detected=not compliant,
        temporal_leakage_detected=temporal_leakage,
        stale_data_detected=stale_data,
        excessive_model_disagreement=False,
        unsupported_claim_ids=[],
        failure_reasons=failure_reasons,
        warnings=warnings,
        recommendation=rec,
    )
