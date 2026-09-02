"""Domain models for portfolio snapshots, mandate evaluation, competition metadata, and sector risk."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import GateStatus
from volagent.domain.risk import RiskCheck


class PortfolioSnapshot(BaseModel):
    """Point-in-time snapshot of the broker account, open strategies, and risk metrics."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    equity: float = Field(ge=0)
    cash: float = Field(ge=0)
    buying_power: float = Field(ge=0)
    initial_nav: float = Field(default=100000.0, gt=0)
    high_water_equity: float = Field(default=100000.0, ge=0)
    daily_realized_pl: float = 0.0
    daily_unrealized_pl: float = 0.0
    open_strategies_count: int = Field(default=0, ge=0)
    new_entries_today_count: int = Field(default=0, ge=0)
    reserved_risk_dollars: float = Field(default=0.0, ge=0)
    sector_reserved_risk: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime
    is_stale: bool = False
    account_id: str | None = None


    @property
    def total_daily_pl(self) -> float:
        return self.daily_realized_pl + self.daily_unrealized_pl

    @property
    def drawdown_from_hwm_pct(self) -> float:
        if self.high_water_equity <= 0:
            return 0.0
        return max(0.0, (self.high_water_equity - self.equity) / self.high_water_equity)


class CompetitionMetadata(BaseModel):
    """Immutable competition metadata registered at first run."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    competition_id: str = "caisheng-options-alpha-2026"
    starting_nav: float = 100000.0
    strategy_version: str = "caisheng-1.0.0"
    mandate_version: str = "caisheng-mandate-v1"
    start_timestamp: datetime
    paper_account_id: str | None = None


class PortfolioRiskReport(BaseModel):
    """Deterministic portfolio-level risk evaluation report against MandateConfig."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_status: GateStatus
    checks: list[RiskCheck]
    approved_quantity: int = 0
    rejection_reasons: list[str] = Field(default_factory=list)
    mandate_version: str = "caisheng-mandate-v1"
    current_equity: float
    reserved_risk_before: float
    reserved_risk_after: float
    risk_reservation_ref: str | None = None
