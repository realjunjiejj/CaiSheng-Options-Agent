"""Data source and execution port interfaces."""

from datetime import datetime
from typing import Any, Protocol
import pandas as pd

from volagent.domain.events import EvidenceItem
from volagent.domain.execution import ExecutionReceipt, OrderPlan
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot


class MarketDataPort(Protocol):
    """Interface for querying market and option chain data."""
    def get_underlying_snapshot(self, symbol: str) -> UnderlyingSnapshot:
        ...

    def get_option_chain(
        self, symbol: str, as_of: datetime | None = None
    ) -> list[OptionContractSnapshot]:
        ...

    def get_underlying_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        ...

    def get_news(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[EvidenceItem]:
        ...


class AccountPort(Protocol):
    """Interface for querying paper account balances and positions."""
    def get_paper_account_equity(self) -> float:
        ...

    def get_positions(self) -> list[dict[str, Any]]:
        ...


class ExecutionPort(Protocol):
    """Interface for multi-leg paper order dispatch."""
    def preview(self, plan: OrderPlan) -> dict[str, Any]:
        ...

    def submit_paper_order(self, plan: OrderPlan) -> ExecutionReceipt:
        ...
