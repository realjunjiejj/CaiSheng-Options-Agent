"""Domain models for scheduled lifecycle runtime, position monitoring, exit triggers, and closed-trade records."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import Decision, ExecutionStatus
from volagent.domain.execution import VerifiedStrategyPositionSnapshot


class ExitTriggerType(str, Enum):
    PROFIT_TARGET = "profit_target"
    MAX_LOSS = "max_loss"
    POST_EVENT_EXPIRATION = "post_event_expiration"
    TIME_STOP = "time_stop"
    SAFETY_HALT = "safety_halt"
    STALE_ORDER_CANCEL_REPLACE = "stale_order_cancel_replace"
    MANUAL_OPERATOR = "manual_operator"


class ExitTrigger(BaseModel):
    """Condition triggering closing of an open strategy."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger_type: ExitTriggerType
    reason: str
    triggered_at: datetime
    estimated_pnl_dollars: float = 0.0
    action_required: bool = True


class PositionMonitorReport(BaseModel):
    """Periodic monitoring report on an open strategy."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    symbol: str
    decision: Decision
    verified_snapshot: VerifiedStrategyPositionSnapshot
    current_mark: float
    entry_cost: float
    unrealized_pnl_dollars: float
    unrealized_pnl_pct: float
    holding_duration_seconds: float
    exit_trigger: ExitTrigger | None = None
    evaluated_at: datetime
    status: str = "OPEN"  # OPEN, EXIT_PENDING, CLOSED, HALTED


class ClosedTradeRecord(BaseModel):
    """Immutable historical record of a fully closed options strategy."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: str
    strategy_id: str
    symbol: str
    decision: Decision
    event_id: str
    entry_order_id: str
    exit_order_id: str
    quantity: int
    entry_price: float
    exit_price: float
    gross_realized_pnl_dollars: float
    fees_and_slippage: float
    net_realized_pnl_dollars: float
    realized_return_pct: float
    max_loss_budget: float
    risk_utilization_pct: float
    opened_at: datetime
    closed_at: datetime
    holding_hours: float
    pre_event_expected_move: float
    pre_event_implied_move: float
    actual_post_event_move: float
    outcome_label: str  # e.g., "WIN", "LOSS", "SCRATCH"
    raw_execution_receipt: dict[str, Any] = Field(default_factory=dict)
