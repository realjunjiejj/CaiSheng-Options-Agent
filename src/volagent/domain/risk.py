"""Risk gate and check models."""

from pydantic import BaseModel, ConfigDict
from volagent.domain.enums import GateStatus


class RiskCheck(BaseModel):
    """Result of an individual deterministic risk gate check."""
    model_config = ConfigDict(extra="forbid")

    name: str
    status: GateStatus
    observed: str
    limit: str
    explanation: str


class RiskReport(BaseModel):
    """Aggregate deterministic risk report across all hard and soft checks."""
    model_config = ConfigDict(extra="forbid")

    overall_status: GateStatus
    checks: list[RiskCheck]
    approved_quantity: int
    rejection_reasons: list[str]
