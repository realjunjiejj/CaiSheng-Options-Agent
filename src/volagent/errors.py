"""Custom exception taxonomy for CaiSheng."""


class VolAgentError(Exception):
    """Base exception for all VolAgent errors."""
    pass


# Compatibility alias
VolAgentException = VolAgentError


class ConfigurationError(VolAgentError):
    """Raised when configuration or environment parameters are invalid."""
    pass


class DataUnavailableError(VolAgentError):
    """Raised when market, options, or replay data is unavailable."""
    pass


class ValidationError(VolAgentError):
    """Raised when domain constraints, schemas, or topological invariants fail."""
    pass


class PricingError(VolAgentError):
    """Raised when option pricing mathematical bounds or calculations fail."""
    pass


class ExecutionError(VolAgentError):
    """Raised when order planning, approval, or execution ledger invariants fail."""
    pass


class RuntimeLockBusyError(ExecutionError):
    """Raised when another valid CaiSheng lifecycle cycle owns the runtime lock."""
    pass


class BrokerExecutionError(ExecutionError):
    """Raised when broker API communication, authentication, or order submission fails."""
    pass


class RiskGateError(VolAgentError):
    """Raised when quantitative risk gate invariants are violated."""
    pass


class ModelRiskError(VolAgentError):
    """Raised when Model-Risk Critic or compliance guards detect violations."""
    pass
