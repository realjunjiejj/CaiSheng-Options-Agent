"""Authoritative DecisionRecord and ShadowBookRecord models for CaiSheng Options Alpha.

Conforms to CAISHENG_WORKPLAN.md Section 5.2 schema `caisheng.decision.v1`.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import Decision


class SnapshotMetadata(BaseModel):
    """Snapshot provenance and point-in-time quote timestamps."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    spot: float
    underlying_quote_time: str
    option_snapshot_time: str
    event_id: str
    event_time: str
    event_source_url: str
    stock_feed: str = "unknown"
    options_feed: str = "unknown"
    options_feed_is_indicative: bool = False


class AgentComponentRuntime(BaseModel):
    """Sanitized execution evidence for one reasoning role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    runtime_mode: Literal[
        "deterministic",
        "llm_assisted",
        "deterministic_fallback",
        "disabled",
    ]
    llm_requested: bool = False
    model_identifier: str | None = None
    latency_ms: int = Field(ge=0, default=0)
    schema_validated: bool = True
    error_type: str | None = None


class AgentRuntimeSummary(BaseModel):
    """Truthful aggregate of which AI/runtime components participated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal[
        "deterministic",
        "llm_assisted",
        "mixed_fallback",
        "deterministic_fallback",
    ] = "deterministic"
    llm_requested: bool = False
    model_identifier: str | None = None
    llm_nodes_succeeded: list[str] = Field(default_factory=list)
    fallback_nodes: list[str] = Field(default_factory=list)
    components: list[AgentComponentRuntime] = Field(default_factory=list)
    deterministic_authority: list[str] = Field(default_factory=lambda: [
        "market_snapshot_validation",
        "pricing",
        "forecast",
        "strategy_selection",
        "sizing",
        "risk",
        "execution",
        "monitoring",
        "reconciliation",
    ])


class VolatilityView(BaseModel):
    """Quantitative volatility metrics and forecast distribution."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    implied_move_bid_pct: float
    implied_move_ask_pct: float
    expected_move_median_pct: float
    q20_pct: float
    q80_pct: float
    expected_iv_crush_points: float
    forecast_confidence: float
    out_of_distribution: bool = False
    ood_reasons: list[str] = Field(default_factory=list)


class StrategyProposal(BaseModel):
    """Evaluation metrics for a candidate strategy structure."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: str  # e.g., "LONG_STRADDLE", "SHORT_IRON_BUTTERFLY"
    executable_edge_pct: float
    expected_pnl_dollars: float
    max_loss_dollars: float
    risk_adjusted_score: float
    rejection_reasons: list[str] = Field(default_factory=list)


class RiskSummary(BaseModel):
    """Portfolio risk checks and mandate reservations."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    mandate_version: str = "caisheng-mandate-v1"
    current_equity: float
    reserved_risk_before: float
    reserved_risk_after: float
    hard_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class CriticSummary(BaseModel):
    """Independent model-risk critic verdict."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation: str = "continue"  # "continue" or "force_no_trade"
    warnings: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """CaiSheng Primary Output Record for every event scan.
    
    Schema: caisheng.decision.v1
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "caisheng.decision.v1"
    decision_id: str
    run_id: str
    strategy_version: str = "caisheng-1.0.0"
    mode: str = "alpaca_paper"
    status: str  # APPROVED, NO_TRADE, BLOCKED, ERROR
    generated_at: str
    snapshot: SnapshotMetadata
    volatility_view: VolatilityView
    proposals: list[StrategyProposal]
    selected_action: str  # "LONG_STRADDLE", "SHORT_IRON_BUTTERFLY", "NO_TRADE"
    selected_strategy_id: str | None = None
    quantity: int = 0
    risk: RiskSummary
    critic: CriticSummary
    agent_runtime: AgentRuntimeSummary = Field(default_factory=AgentRuntimeSummary)
    artifact_hash: str = ""

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 hash of all decision content excluding artifact_hash."""
        data = self.model_dump(mode="json", exclude={"artifact_hash"})
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def create_and_hash(cls, **kwargs: Any) -> "DecisionRecord":
        """Construct DecisionRecord and compute canonical artifact_hash."""
        kwargs.pop("artifact_hash", None)
        record = cls(artifact_hash="", **kwargs)
        h = record.compute_hash()
        return cls(artifact_hash=h, **kwargs)


class ShadowProposal(BaseModel):
    """Counterfactual evaluation of a candidate strategy structure."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: str
    executable: bool
    simulated_entry_price: float
    simulated_exit_price: float
    counterfactual_pnl_dollars: float
    rejection_reason: str = ""


class ShadowBookRecord(BaseModel):
    """Immutable record comparing chosen strategy vs unselected alternatives after event outcome."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    shadow_id: str
    event_id: str
    symbol: str
    selected_action: str
    selected_strategy_pnl: float
    counterfactual_proposals: list[ShadowProposal]
    actual_post_event_move: float
    actual_iv_crush_points: float
    recorded_at: str
