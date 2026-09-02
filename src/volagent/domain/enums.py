"""Enumerations for VolAgent domain models."""

from enum import Enum


class EventTiming(str, Enum):
    BEFORE_MARKET_OPEN = "bmo"
    AFTER_MARKET_CLOSE = "amc"
    DURING_MARKET_HOURS = "dmh"


class OpportunityKind(str, Enum):
    EARNINGS_EVENT = "earnings_event"
    MACRO_EVENT = "macro_event"
    DAILY_VOLATILITY = "daily_volatility"


class Decision(str, Enum):
    LONG_STRADDLE = "long_straddle"
    SHORT_IRON_BUTTERFLY = "short_iron_butterfly"
    NO_TRADE = "no_trade"


class GateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RunStatus(str, Enum):
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class DataMode(str, Enum):
    REPLAY_REAL = "replay_real"
    REPLAY_SYNTHETIC = "replay_synthetic"
    LIVE = "live"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PositionIntent(str, Enum):
    BUY_TO_OPEN = "buy_to_open"
    SELL_TO_OPEN = "sell_to_open"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_CLOSE = "sell_to_close"


class ExecutionStatus(str, Enum):
    SIMULATED = "simulated"
    PREVIEWED = "previewed"
    APPROVED = "approved"
    INTENT_PERSISTED = "intent_persisted"
    SUBMITTING = "submitting"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    CLOSED = "closed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class BrokerTarget(str, Enum):
    ALPACA_PAPER = "alpaca_paper"
    SIMULATED_LOCAL = "simulated_local"


class NetPriceConvention(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class AbstentionReason(str, Enum):
    NONE = "none"
    NO_EDGE = "no_edge"
    DATA_QUALITY = "data_quality"
    RISK_LIMIT = "risk_limit"
    CRITIC_VETO = "critic_veto"
    SYSTEM_ERROR = "system_error"
