"""Option strategy candidate and leg models."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import Decision


class OptionLeg(BaseModel):
    """Specification of an individual option leg in a multi-leg strategy."""
    model_config = ConfigDict(extra="forbid")

    contract_symbol: str
    option_type: Literal["call", "put"]
    strike: float
    expiration: date
    side: Literal["buy", "sell"]
    position_intent: Literal["buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"]
    ratio_qty: int = Field(default=1, ge=1)
    entry_price_assumption: float
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0


class StrategyCandidate(BaseModel):
    """Candidate multi-leg option strategy with evaluated metrics and payoff."""
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    decision: Decision
    legs: list[OptionLeg]
    quantity: int = Field(ge=0)
    entry_debit_credit: float  # Positive = debit paid, negative = credit received
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    max_loss: float  # Positive loss magnitude
    max_profit: float | None = None
    break_evens: list[float] = Field(default_factory=list)
    expected_pnl: float = 0.0
    expected_shortfall_95: float = 0.0
    risk_adjusted_score: float = 0.0
    stress_losses: dict[str, float] = Field(default_factory=dict)
    liquidity_score: float = 0.85
