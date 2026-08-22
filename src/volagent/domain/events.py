"""Earnings event and evidence domain models."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

from volagent.domain.enums import EventTiming
from volagent.provenance import Provenance


class EarningsEvent(BaseModel):
    """Earnings event record with point-in-time decision and exit timestamps."""
    model_config = ConfigDict(extra="ignore")

    event_id: str
    symbol: str
    fiscal_period: str | None = None
    event_time: datetime
    timing: EventTiming
    confirmed: bool
    decision_time: datetime
    exit_time: datetime
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def map_quarter_alias(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "fiscal_quarter" in values and "fiscal_period" not in values:
                values["fiscal_period"] = values["fiscal_quarter"]
        return values


class EvidenceItem(BaseModel):
    """Factual, point-in-time evidence piece with unique ID and confidence."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    category: str = "filing"
    claim: str = ""
    magnitude_relevance: str = ""
    numeric_value: float | None = None
    units: str | None = None
    confidence: float = 0.8
    observed_at: datetime | None = None
    provenance: Provenance | None = None

    @model_validator(mode="before")
    @classmethod
    def map_source_type_alias(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "source_type" in values and "category" not in values:
                values["category"] = values["source_type"]
            if "summary" in values and "claim" not in values:
                values["claim"] = values["summary"]
            if "metric_name" in values and "magnitude_relevance" not in values:
                values["magnitude_relevance"] = values["metric_name"]
        return values

    @property
    def source_type(self) -> str:
        return self.category

    @property
    def summary(self) -> str:
        return self.claim

    @property
    def metric_name(self) -> str:
        return self.magnitude_relevance
