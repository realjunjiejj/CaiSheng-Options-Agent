"""Market and option contract domain models."""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

from volagent.provenance import Provenance


class UnderlyingSnapshot(BaseModel):
    """Point-in-time quote and volatility snapshot of the underlying stock/ETF."""
    model_config = ConfigDict(extra="forbid")

    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    quote_time: datetime
    previous_close: float | None = None
    realized_vol_10d: float | None = None
    realized_vol_30d: float | None = None
    provenance: Provenance


class OptionContractSnapshot(BaseModel):
    """Point-in-time quote and Greek snapshot for an individual option contract."""
    model_config = ConfigDict(extra="forbid")

    symbol: str
    underlying_symbol: str
    option_type: Literal["call", "put"]
    strike: float
    expiration: date
    bid: float
    ask: float
    last: float | None = None
    quote_time: datetime
    volume: int | None = None
    open_interest: int | None = None
    vendor_implied_vol: float | None = None
    vendor_delta: float | None = None
    vendor_gamma: float | None = None
    vendor_theta: float | None = None
    vendor_vega: float | None = None
    multiplier: int = 100
    provenance: Provenance
