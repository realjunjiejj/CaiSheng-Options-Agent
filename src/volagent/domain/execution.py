"""Domain models for execution, order planning, receipts, and broker-verified positions."""

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import BrokerTarget, ExecutionStatus, NetPriceConvention, OptionType, OrderSide, PositionIntent


class ApprovedLegSnapshot(BaseModel):
    """Enriched immutable snapshot of an approved option leg with raw market quotes."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_symbol: str
    underlying_symbol: str
    option_type: OptionType
    strike: float = Field(gt=0)
    expiration: date
    side: OrderSide
    ratio_qty: int = Field(ge=1, default=1)
    position_intent: PositionIntent
    bid: float = Field(ge=0)
    ask: float = Field(ge=0)
    multiplier: int = Field(default=100, ge=1)
    vendor_implied_vol: float = Field(ge=0, default=0.50)
    vendor_delta: float = Field(ge=-1.0, le=1.0, default=0.0)
    quote_time: datetime
    entry_price_assumption: float = Field(ge=0)


class VerifiedPositionLeg(BaseModel):
    """Immutable snapshot of an individual option position leg verified against the broker."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_symbol: str
    symbol: str
    qty: int
    side: str  # "long" or "short"
    avg_entry_price: float = Field(ge=0)


class VerifiedStrategyPositionSnapshot(BaseModel):
    """Authoritative, timestamped broker position evidence for a strategy before closing."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    symbol: str
    timestamp: datetime
    positions: list[VerifiedPositionLeg]
    evidence_source: str = "alpaca_paper"


class OrderPlan(BaseModel):
    """Immutable, fingerprinted multi-leg options order plan with complete identity and exposure keys."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_order_id: str
    approval_token: str
    symbol: str
    decision: str
    quantity: int = Field(gt=0)
    net_price_convention: NetPriceConvention
    limit_price: float = Field(gt=0)
    legs: list[ApprovedLegSnapshot]
    fingerprint: str
    economic_fingerprint: str = ""
    logical_exposure_key: str = ""
    execution_fingerprint: str = ""
    strategy_id: str | None = None
    decision_id: str = "dec-default"
    event_id: str = "evt-default"
    model_version: str = "caisheng-1.0.0"
    mandate_version: str = "caisheng-mandate-v1"
    decision_time_bucket: str = ""
    risk_reservation_ref: str | None = None
    quote_provenance_id: str | None = None
    original_entry_intent_id: str | None = None
    broker_target: BrokerTarget = BrokerTarget.SIMULATED_LOCAL
    created_at: datetime
    expires_at: datetime
    max_loss_dollars: float = Field(ge=0)
    estimated_cost_dollars: float = Field(ge=0)


class ExecutionReceipt(BaseModel):
    """Immutable execution receipt returned by the broker or simulator."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str
    client_order_id: str
    broker_order_id: str
    broker_target: BrokerTarget
    status: ExecutionStatus
    submitted_at: datetime
    filled_at: datetime | None = None
    filled_quantity: int = 0
    average_price: float | None = None
    fingerprint: str
    logical_exposure_key: str = ""
    raw_broker_response: dict[str, Any] = Field(default_factory=dict)
    rejection_reason: str | None = None
    reconciliation_evidence_id: str | None = None
