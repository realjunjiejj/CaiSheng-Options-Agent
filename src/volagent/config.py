"""Central configuration management with YAML loading, aliases, and environment variables."""

import os
from pathlib import Path
from typing import Any, Literal
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from volagent.errors import ConfigurationError

def _resolve_project_root() -> Path:
    if env_root := os.environ.get("PROJECT_ROOT"):
        p = Path(env_root).resolve()
        if p.exists():
            return p
    cwd = Path.cwd().resolve()
    if (cwd / "config").is_dir() or (cwd / "src").is_dir():
        return cwd
    app_dir = Path("/app")
    if (app_dir / "config").is_dir():
        return app_dir
    curr = Path(__file__).resolve()
    for parent in curr.parents:
        if (parent / "config").is_dir():
            return parent
    return curr.parent.parent.parent

# Base directory of the repository or container deployment
PROJECT_ROOT = _resolve_project_root()


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "CaiSheng"
    environment: str = "demo"
    timezone: str = "UTC"
    random_seed: int = 42
    max_graph_runtime_seconds: int = Field(gt=0, default=60)
    log_level: str = "INFO"
    llm_timeout_seconds: int = Field(gt=0, default=15)
    llm_retries: int = Field(ge=0, default=1)
    cache_ttl_seconds: int = Field(ge=0, default=300)


class ContractFiltersConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    min_dte_days: int = Field(ge=0, default=1)
    max_dte_days: int = Field(gt=0, default=30)
    max_atm_distance_pct: float = Field(gt=0, default=0.15)
    max_relative_spread_pct: float = Field(gt=0, default=0.20)
    min_volume: int = Field(ge=0, default=50)
    min_open_interest: int = Field(ge=0, default=100)
    max_quote_age_seconds: int = Field(gt=0, default=1800)
    clock_skew_tolerance_seconds: int = Field(ge=0, le=5, default=2)

    @model_validator(mode="before")
    @classmethod
    def map_yaml_aliases(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "min_days_after_event" in values and "min_dte_days" not in values:
                values["min_dte_days"] = values["min_days_after_event"]
            if "max_days_after_event" in values and "max_dte_days" not in values:
                values["max_dte_days"] = values["max_days_after_event"]
            if "min_daily_volume" in values and "min_volume" not in values:
                values["min_volume"] = values["min_daily_volume"]
            if "max_relative_spread" in values and "max_relative_spread_pct" not in values:
                values["max_relative_spread_pct"] = values["max_relative_spread"]
        return values


# Backwards compatibility alias
ContractsConfig = ContractFiltersConfig


class MarketDataConfig(BaseModel):
    """Explicit Alpaca feed choices carried into every live decision receipt."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    stock_feed: Literal["iex", "sip"] = "iex"
    options_feed: Literal["indicative", "opra"] = "indicative"


class ForecastConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    min_training_events: int = Field(gt=0, default=10)
    confidence_floor: float = Field(ge=0.0, le=1.0, default=0.60)
    edge_buffer_pct_spot: float = Field(ge=0.0, default=0.0025)
    monte_carlo_scenarios: int = Field(gt=100, default=3000)
    vrp_discount_ratio: float = Field(ge=0.5, le=1.0, default=0.85)
    student_t_tail_df: float = Field(ge=2.0, le=10.0, default=3.5)
    model_mode: str = "hybrid_vrp"
    residual_shrinkage_weight: float = Field(ge=0.0, le=1.0, default=0.35)
    require_confidence_bound_edge: bool = False
    minimum_ev_to_max_loss: float = Field(ge=0.0, le=1.0, default=0.0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hard_max_risk_nav_pct: float = Field(gt=0.0, le=0.05, default=0.01)  # 1.0% Hard Cap
    recommended_risk_nav_pct: float = Field(gt=0.0, le=0.02, default=0.005)  # 0.5% Target
    max_abs_dollar_delta_nav_pct: float = Field(gt=0.0, le=0.10, default=0.02)  # 2.0% NAV Delta
    max_stress_loss_nav_pct: float = Field(gt=0.0, le=0.05, default=0.01)  # 1.0% NAV Stress Cap
    max_contracts: int = Field(gt=0, default=20)
    require_defined_risk_for_short_vol: bool = True
    reject_dividend_before_expiry: bool = True

class MandateConfig(BaseModel):
    """CaiSheng Competition Portfolio Mandate and Autonomous Risk Limits."""
    model_config = ConfigDict(extra="ignore", frozen=True)
    competition_initial_nav: float = Field(gt=0, default=100000.0)
    recommended_max_loss_per_strategy: float = Field(gt=0, default=500.0)  # 0.50% initial NAV
    absolute_max_loss_nav_pct: float = Field(gt=0.0, le=0.05, default=0.01)  # 1.00% current equity
    max_open_strategies: int = Field(gt=0, default=3)
    max_new_entries_per_day: int = Field(gt=0, default=2)
    max_total_reserved_risk_nav_pct: float = Field(gt=0.0, le=0.10, default=0.02)  # 2.00% current equity
    max_same_sector_reserved_risk: float = Field(gt=0, default=1000.0)
    daily_loss_halt_dollars: float = Field(gt=0, default=1500.0)  # Realized + Unrealized Loss Halt
    drawdown_halt_pct: float = Field(gt=0.0, le=0.20, default=0.05)  # 5.00% from HWM
    strategy_multiplier: int = Field(default=100)
    mandate_version: str = "caisheng-mandate-v1"


class ExecutionConfig(BaseModel):

    model_config = ConfigDict(extra="ignore")
    paper_only: bool = True
    require_human_approval: bool = True
    allow_order_submission: bool = False  # Strict kill switch, False by default
    order_type: str = "limit"
    time_in_force: str = "day"
    limit_improvement_fraction: float = Field(ge=0.0, le=1.0, default=0.25)
    slippage_per_contract: float = Field(ge=0.0, default=0.02)
    fee_per_contract: float = Field(ge=0.0, default=0.65)


class CompetitionConfig(BaseModel):
    """Explicit, lease-gated paper competition settings."""

    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    lease_required: bool = True
    lease_path: str = "data/runtime/competition_arm.json"
    arm_duration_hours: int = Field(gt=0, le=24, default=8)
    daily_volatility_symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    scan_start_et: str = "10:15"
    scan_end_et: str = "14:30"


class VolAgentSettings(BaseSettings):
    """Unified application settings model supporting .env and flexible env vars."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="VOLAGENT_",
    )

    application: ApplicationConfig = Field(default_factory=ApplicationConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    contracts: ContractFiltersConfig = Field(default_factory=ContractFiltersConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    mandate: MandateConfig = Field(default_factory=MandateConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    competition: CompetitionConfig = Field(default_factory=CompetitionConfig)

    volagent_env: str = "demo"
    volagent_data_mode: str = "replay_synthetic"
    volagent_replay_scenario_id: str | None = None
    volagent_allow_order_submission: bool = False
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper_trade: bool = True

    @field_validator("alpaca_paper_trade")
    def enforce_paper_only(cls, v: bool) -> bool:
        if not v:
            raise ConfigurationError("ALPACA_PAPER_TRADE must be True. Live trading is strictly prohibited.")
        return v


def load_config(config_path: str | Path | None = None) -> VolAgentSettings:
    """Load configuration resolving paths relative to project root with clear precedence."""
    settings = VolAgentSettings()
    dot_env_values = dotenv_values(PROJECT_ROOT / ".env")

    def configured_value(name: str) -> str | None:
        """Use explicit process variables first, then the project .env file."""
        if name in os.environ:
            return os.environ[name]
        value = dot_env_values.get(name)
        return str(value) if value is not None else None

    if config_path is None:
        target_file = PROJECT_ROOT / "config" / "demo.yaml"
        if not target_file.exists():
            target_file = PROJECT_ROOT / "config" / "default.yaml"
    else:
        target_file = Path(config_path)
        if not target_file.is_absolute():
            if (Path.cwd() / target_file).exists():
                target_file = (Path.cwd() / target_file).resolve()
            elif (PROJECT_ROOT / target_file).exists():
                target_file = (PROJECT_ROOT / target_file).resolve()
            elif (Path("/app") / target_file).exists():
                target_file = (Path("/app") / target_file).resolve()
            else:
                target_file = (PROJECT_ROOT / target_file).resolve()

    declared_data_mode: str | None = None
    if target_file.exists():
        with open(target_file, "r") as f:
            data = yaml.safe_load(f) or {}

        if "application" in data:
            settings.application = ApplicationConfig(**data["application"])
        if "market_data" in data:
            settings.market_data = MarketDataConfig(**data["market_data"])
        if "contracts" in data:
            settings.contracts = ContractFiltersConfig(**data["contracts"])
        if "forecast" in data:
            settings.forecast = ForecastConfig(**data["forecast"])
        if "risk" in data:
            settings.risk = RiskConfig(**data["risk"])
        if "mandate" in data:
            settings.mandate = MandateConfig(**data["mandate"])
        if "execution" in data:
            settings.execution = ExecutionConfig(**data["execution"])
        if "competition" in data:
            settings.competition = CompetitionConfig(**data["competition"])
        if "volagent_data_mode" in data:
            declared_data_mode = str(data["volagent_data_mode"])
            settings.volagent_data_mode = declared_data_mode
    elif config_path is not None:
        raise ConfigurationError(f"Explicitly specified config file not found: {target_file}")

    # Load documented unprefixed variables. BaseSettings has a VOLAGENT_ prefix,
    # so these must be read explicitly from the project .env file as well.
    if data_mode := configured_value("VOLAGENT_DATA_MODE") or configured_value("DATA_MODE"):
        settings.volagent_data_mode = data_mode
    if api_key := configured_value("ALPACA_API_KEY"):
        settings.alpaca_api_key = api_key
    if secret_key := configured_value("ALPACA_SECRET_KEY"):
        settings.alpaca_secret_key = secret_key

    paper_trade = configured_value("ALPACA_PAPER_TRADE")
    if paper_trade is not None and paper_trade.strip().lower() not in ("true", "1", "yes"):
        raise ConfigurationError("ALPACA_PAPER_TRADE must be True. Live trading is strictly prohibited.")
    settings.alpaca_paper_trade = True

    # The write switch is deliberately process-scoped. A persistent .env file
    # may contain credentials and read settings, but it must never silently
    # re-arm order submission after a restart or incident. Competition YAML is
    # an upper-level policy declaration; an explicit process variable remains
    # mandatory for the current process to write.
    allow_order_submission = os.environ.get("VOLAGENT_ALLOW_ORDER_SUBMISSION")
    val = (
        allow_order_submission.strip().lower() in ("true", "1", "yes")
        if allow_order_submission is not None
        else False
    )
    settings.execution.allow_order_submission = val
    settings.volagent_allow_order_submission = val

    require_human_approval = configured_value("VOLAGENT_REQUIRE_HUMAN_APPROVAL")
    if require_human_approval is not None:
        settings.execution.require_human_approval = (
            require_human_approval.strip().lower() in ("true", "1", "yes")
        )

    # Competition configuration is a sealed, hash-bound safety policy. A stale
    # developer .env must not silently turn its live analysis back into replay.
    if settings.competition.enabled and declared_data_mode is not None:
        settings.volagent_data_mode = declared_data_mode

    return settings
