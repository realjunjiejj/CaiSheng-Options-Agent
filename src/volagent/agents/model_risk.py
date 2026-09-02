"""Model-Risk Critic and Track Compliance Guard with comprehensive directional scan and temporal audit."""

from datetime import datetime, timezone
from typing import Any

from volagent.domain.enums import GateStatus
from volagent.domain.events import EarningsEvent, EvidenceItem
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
    "upside potential",
    "downside target",
    "rally",
    "dump",
]


def validate_track_compliance(
    long_thesis: VolatilityThesis | None,
    short_thesis: VolatilityThesis | None,
    extra_texts: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Strictly audit all agent text fields to prevent directional bias."""
    violations = []
    texts_to_check = []

    if long_thesis:
        if long_thesis.directional_view != "none":
            violations.append(f"Long-Vol Advocate leaked directional view: {long_thesis.directional_view}")
        texts_to_check.append(long_thesis.thesis.lower())
        texts_to_check.append(long_thesis.numeric_argument.lower())
        for inv in long_thesis.invalidation_conditions:
            texts_to_check.append(inv.lower())

    if short_thesis:
        if short_thesis.directional_view != "none":
            violations.append(f"Short-Vol Advocate leaked directional view: {short_thesis.directional_view}")
        texts_to_check.append(short_thesis.thesis.lower())
        texts_to_check.append(short_thesis.numeric_argument.lower())
        for inv in short_thesis.invalidation_conditions:
            texts_to_check.append(inv.lower())

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
    evidence: list[EvidenceItem] | None = None,
    llm_client: Any = None,
    require_advocates: bool = True,
) -> CriticReport:
    """Independent risk and compliance audit. Can force NO_TRADE."""
    failure_reasons = []
    warnings = []

    # 1. Check missing advocate roles (P1-21 Fix)
    if require_advocates and (long_thesis is None or short_thesis is None):
        failure_reasons.append("Missing required advocate thesis (Long-Vol or Short-Vol agent failed to report).")

    # 2. Stale quote audit: check quote age against decision time
    # In a real historical replay, age is measured relative to its locked
    # historical decision boundary—not wall-clock time today.
    reference_time = event.decision_time
    age_seconds = (reference_time - underlying.quote_time).total_seconds()
    stale_data = age_seconds > 1800 or age_seconds < 0

    if stale_data:
        failure_reasons.append(f"Stale or invalid market quotes (Age: {age_seconds/60:.1f} minutes).")

    # 3. Temporal leakage: every input must be observable by the locked decision
    # cutoff. This also supports an ongoing daily-volatility opportunity whose
    # scan-start timestamp naturally precedes the market-data fetch.
    temporal_leakage = (underlying.quote_time > event.decision_time) or any(
        c.quote_time > event.decision_time for c in option_chain
    )
    if evidence:
        for ev in evidence:
            ev_time = ev.observed_at or (ev.provenance.observed_at if ev.provenance else None)
            if ev_time and ev_time > event.decision_time:
                temporal_leakage = True
                failure_reasons.append(f"Temporal leakage in evidence: {ev.evidence_id} observed at {ev_time.isoformat()} after decision time.")

    if temporal_leakage:
        failure_reasons.append("Temporal leakage detected: Market quotes or evidence observed after decision cutoff.")

    # 4. Chain Liquidity audit
    if len(option_chain) < 2:
        failure_reasons.append("Insufficient liquid options chain available for strategy construction.")

    # 5. Out-of-Distribution audit
    if move_forecast.out_of_distribution:
        failure_reasons.append("Quantitative forecast feature vector flagged as Out-Of-Distribution.")

    # 6. Options Alpha Compliance Audit (P1-20 Fix)
    compliant, dir_violations = validate_track_compliance(long_thesis, short_thesis)
    if not compliant:
        failure_reasons.extend(dir_violations)

    # 7. Model Disagreement Metric (P1-22 Fix)
    excessive_disagreement = False
    if long_thesis and short_thesis:
        if long_thesis.confidence >= 0.80 and short_thesis.confidence >= 0.80:
            excessive_disagreement = True
            warnings.append("High model disagreement: Both Long and Short advocates claim >= 80% confidence.")

    status = GateStatus.FAIL if failure_reasons else GateStatus.PASS
    rec = "force_no_trade" if failure_reasons else "continue"

    return CriticReport(
        status=status,
        directional_leakage_detected=not compliant,
        temporal_leakage_detected=temporal_leakage,
        stale_data_detected=stale_data,
        excessive_model_disagreement=excessive_disagreement,
        unsupported_claim_ids=[],
        failure_reasons=failure_reasons,
        warnings=warnings,
        recommendation=rec,
    )
