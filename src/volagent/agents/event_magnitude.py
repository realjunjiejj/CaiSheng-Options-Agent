"""Event Magnitude Analyst Agent."""

import json
from typing import Any
from volagent.agents.prompts import EVENT_MAGNITUDE_PROMPT
from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.state import EventMagnitudeAssessment


def run_event_magnitude_agent(
    event: EarningsEvent,
    evidence: list[EvidenceItem],
    llm_client: Any = None,
) -> EventMagnitudeAssessment:
    """Assess event uncertainty and novelty magnitude from point-in-time evidence."""
    if not evidence:
        return EventMagnitudeAssessment(
            directional_view="none",
            event_novelty_score=0.5,
            guidance_uncertainty_score=0.5,
            analyst_dispersion_score=0.5,
            magnitude_pressure_score=0.5,
            confidence=0.5,
            supporting_evidence_ids=[],
            summary="No specific point-in-time textual evidence available; defaulted to neutral prior.",
            missing_information=["earnings_transcript", "analyst_dispersion", "sec_8k"],
        )

    # If live LLM is provided
    if llm_client is not None:
        try:
            prompt_input = f"""Event: {event.symbol} {event.fiscal_period or ''} at {event.event_time.isoformat()}
Evidence items:
{json.dumps([e.model_dump(mode='json') for e in evidence], indent=2)}
"""
            structured_llm = llm_client.with_structured_output(EventMagnitudeAssessment)
            result = structured_llm.invoke([
                {"role": "system", "content": EVENT_MAGNITUDE_PROMPT},
                {"role": "user", "content": prompt_input},
            ])
            return result
        except Exception:
            pass  # Fall back to deterministic evidence synthesizer

    # Deterministic high-fidelity evidence synthesizer (for Replay & Zero-Key Demo)
    evidence_ids = [e.evidence_id for e in evidence]
    categories = {e.category: e for e in evidence}

    novelty = 0.5
    uncertainty = 0.5
    dispersion = 0.5

    if "guidance_uncertainty" in categories:
        uncertainty = categories["guidance_uncertainty"].numeric_value or 0.75
    if "analyst_dispersion" in categories:
        dispersion = categories["analyst_dispersion"].numeric_value or 0.65
    if "earnings_history" in categories:
        novelty = min(1.0, (categories["earnings_history"].numeric_value or 0.08) * 10.0)

    mag_pressure = 0.4 * uncertainty + 0.35 * dispersion + 0.25 * novelty
    avg_conf = sum(e.confidence for e in evidence) / max(1, len(evidence))

    summary = (
        f"Analyzed {len(evidence)} point-in-time evidence items for {event.symbol}. "
        f"Key uncertainty drivers include guidance dispersion and historical jump variance."
    )

    return EventMagnitudeAssessment(
        directional_view="none",
        event_novelty_score=float(novelty),
        guidance_uncertainty_score=float(uncertainty),
        analyst_dispersion_score=float(dispersion),
        magnitude_pressure_score=float(mag_pressure),
        confidence=float(avg_conf),
        supporting_evidence_ids=evidence_ids,
        conflicting_evidence_ids=[],
        summary=summary,
        missing_information=[],
    )
