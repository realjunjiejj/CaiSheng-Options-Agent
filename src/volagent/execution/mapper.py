"""Centralized, fail-closed broker status and fill metric mapper for Alpaca and CaiSheng."""

from typing import Any
from volagent.domain.enums import ExecutionStatus


def map_broker_status(raw_status: Any) -> ExecutionStatus:
    """Map broker order status string to ExecutionStatus enum with strict fail-closed UNKNOWN fallback."""
    if raw_status is None:
        return ExecutionStatus.UNKNOWN

    status_str = str(raw_status).lower().replace("orderstatus.", "").strip()

    status_map = {
        "accepted": ExecutionStatus.ACCEPTED,
        "new": ExecutionStatus.ACCEPTED,
        "pending_new": ExecutionStatus.ACCEPTED,
        "partially_filled": ExecutionStatus.PARTIALLY_FILLED,
        "filled": ExecutionStatus.FILLED,
        "canceled": ExecutionStatus.CANCELED,
        "stopped": ExecutionStatus.CANCELED,
        "rejected": ExecutionStatus.REJECTED,
        "expired": ExecutionStatus.REJECTED,
    }

    # Strict fail-closed: unmapped status must return UNKNOWN, never ACCEPTED
    return status_map.get(status_str, ExecutionStatus.UNKNOWN)


def extract_fill_metrics(broker_order: Any) -> tuple[int, float | None]:
    """Extract actual filled quantity and verified average fill price.

    Rules:
    - If filled_qty == 0: average_price MUST be None.
    - Never substitute limit_price for average_price when unfilled.
    """
    if broker_order is None:
        return 0, None

    if isinstance(broker_order, dict):
        raw_qty = broker_order.get("filled_qty", 0)
        raw_avg_px = broker_order.get("filled_avg_price")
    else:
        raw_qty = getattr(broker_order, "filled_qty", 0)
        raw_avg_px = getattr(broker_order, "filled_avg_price", None)

    try:
        filled_qty = int(float(raw_qty or 0))
    except (ValueError, TypeError):
        filled_qty = 0

    if filled_qty <= 0:
        return 0, None

    if raw_avg_px is not None:
        try:
            return filled_qty, float(raw_avg_px)
        except (ValueError, TypeError):
            return filled_qty, None

    return filled_qty, None
