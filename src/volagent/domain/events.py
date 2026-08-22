"""Earnings event and evidence domain models."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

from volagent.domain.enums import EventTiming
from volagent.provenance import Provenance


class EarningsEvent(BaseModel):
    """Earnings event record with point-in-time decision and exit timestamps."""
    model_config = ConfigDict(extra="forbid")

    event_id: str
    symbol: str
    fiscal_period: str | None = None
    event_time: datetime
    timing: EventTiming
    confirmed: bool
    decision_time: datetime
    exit_time: datetime
    provenance: Provenance


class EvidenceItem(BaseModel):
    """Factual, point-in-time evidence piece with unique ID and confidence."""
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    category: Literal[
        "filing",
        "earnings_history",
        "guidance_uncertainty",
        "analyst_dispersion",
        "news_novelty",
        "macro_context",
        "market_data",
        "option_surface",
    ]
    claim: str
    magnitude_relevance: str
    numeric_value: float | None = None
    units: str | None = None
    confidence: float
    provenance: Provenance
