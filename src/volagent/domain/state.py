"""LangGraph state definition and agent structured output models."""

import operator
from typing import Annotated, Any, Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import AbstentionReason, DataMode, Decision, GateStatus, RunStatus
from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.execution import ExecutionReceipt, OrderPlan
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.risk import RiskReport
from volagent.domain.strategies import StrategyCandidate


class EventMagnitudeAssessment(BaseModel):
    """Structured assessment produced by EventMagnitudeAgent."""
    model_config = ConfigDict(extra="forbid")

    directional_view: Literal["none"] = "none"
    event_novelty_score: float = Field(ge=0.0, le=1.0)
    guidance_uncertainty_score: float = Field(ge=0.0, le=1.0)
    analyst_dispersion_score: float = Field(ge=0.0, le=1.0)
    magnitude_pressure_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str]
    conflicting_evidence_ids: list[str] = []
    summary: str
    missing_information: list[str] = []


class VolatilityThesis(BaseModel):
    """Structured thesis produced by LongVolAdvocate or ShortVolAdvocate."""
    model_config = ConfigDict(extra="forbid")

    side: Literal["long_vol", "short_vol"]
    directional_view: Literal["none"] = "none"
    thesis: str
    numeric_argument: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = []
    invalidation_conditions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    support_score: float = Field(ge=0.0, le=1.0, default=0.5)


class CriticReport(BaseModel):
    """Structured audit report produced by ModelRiskCritic."""
    model_config = ConfigDict(extra="forbid")

    status: GateStatus
    directional_leakage_detected: bool
    temporal_leakage_detected: bool
    stale_data_detected: bool
    excessive_model_disagreement: bool
    unsupported_claim_ids: list[str] = []
    failure_reasons: list[str] = []
    warnings: list[str] = []
    recommendation: Literal["continue", "force_no_trade"]


def merge_dicts(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    res = {}
    if a:
        res.update(a)
    if b:
        res.update(b)
    return res


def deduplicate_list(a: list[str] | None, b: list[str] | None) -> list[str]:
    combined = []
    seen = set()
    for item in (a or []) + (b or []):
        if item not in seen:
            seen.add(item)
            combined.append(item)
    return combined


class VolAgentState(TypedDict, total=False):
    """Strongly typed LangGraph state with strict trust boundaries and reducer annotations."""
    run_id: str
    status: RunStatus
    final_decision: Decision
    abstention_reason: AbstentionReason
    mode: DataMode
    symbol: str
    event: EarningsEvent
    underlying: UnderlyingSnapshot
    option_chain: list[OptionContractSnapshot]
    evidence: list[EvidenceItem]
    feature_set: Annotated[dict[str, Any], merge_dicts]
    event_assessment: EventMagnitudeAssessment
    move_forecast: MoveForecast
    iv_forecast: IVCrushForecast
    long_vol_thesis: VolatilityThesis
    short_vol_thesis: VolatilityThesis
    critic_report: CriticReport
    candidates: list[StrategyCandidate]
    approved_candidate: StrategyCandidate | None
    audit_proposal: StrategyCandidate | None
    risk_report: RiskReport
    order_plan: OrderPlan | None
    execution_receipt: ExecutionReceipt | None
    rejection_reasons: Annotated[list[str], deduplicate_list]
    trace_events: Annotated[list[dict[str, Any]], operator.add]
    artifact_hashes: dict[str, str]
