"""Central configuration management with YAML loading, aliases, and environment variables."""

import os
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from volagent.errors import ConfigurationError

# Base directory of the repository (4 levels up from this file: src/volagent/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "VolAgent Alpha"
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


class ForecastConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    min_training_events: int = Field(gt=0, default=10)
    confidence_floor: float = Field(ge=0.0, le=1.0, default=0.60)
    edge_buffer_pct_spot: float = Field(ge=0.0, default=0.0025)
    monte_carlo_scenarios: int = Field(gt=100, default=3000)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hard_max_risk_nav_pct: float = Field(gt=0.0, le=0.05, default=0.01)  # 1.0% Hard Cap
    recommended_risk_nav_pct: float = Field(gt=0.0, le=0.02, default=0.005)  # 0.5% Target
    max_abs_dollar_delta_nav_pct: float = Field(gt=0.0, le=0.10, default=0.02)  # 2.0% NAV Delta
    max_stress_loss_nav_pct: float = Field(gt=0.0, le=0.05, default=0.01)  # 1.0% NAV Stress Cap
    max_contracts: int = Field(gt=0, default=20)
    require_defined_risk_for_short_vol: bool = True
    reject_dividend_before_expiry: bool = True


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


class VolAgentSettings(BaseSettings):
    """Unified application settings model supporting .env and flexible env vars."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="VOLAGENT_",
    )

    application: ApplicationConfig = Field(default_factory=ApplicationConfig)
    contracts: ContractFiltersConfig = Field(default_factory=ContractFiltersConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

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

    if config_path is None:
        target_file = PROJECT_ROOT / "config" / "demo.yaml"
        if not target_file.exists():
            target_file = PROJECT_ROOT / "config" / "default.yaml"
    else:
        target_file = Path(config_path)
        if not target_file.is_absolute():
            target_file = PROJECT_ROOT / target_file

    if target_file.exists():
        with open(target_file, "r") as f:
            data = yaml.safe_load(f) or {}

        if "application" in data:
            settings.application = ApplicationConfig(**data["application"])
        if "contracts" in data:
            settings.contracts = ContractFiltersConfig(**data["contracts"])
        if "forecast" in data:
            settings.forecast = ForecastConfig(**data["forecast"])
        if "risk" in data:
            settings.risk = RiskConfig(**data["risk"])
        if "execution" in data:
            settings.execution = ExecutionConfig(**data["execution"])
    elif config_path is not None:
        raise ConfigurationError(f"Explicitly specified config file not found: {target_file}")

    # Fallback to direct environment variables without prefix
    if os.environ.get("DATA_MODE"):
        settings.volagent_data_mode = os.environ["DATA_MODE"]
    if os.environ.get("ALPACA_API_KEY"):
        settings.alpaca_api_key = os.environ["ALPACA_API_KEY"]
    if os.environ.get("ALPACA_SECRET_KEY"):
        settings.alpaca_secret_key = os.environ["ALPACA_SECRET_KEY"]

    # Enforce kill switch override from env if set
    if os.environ.get("VOLAGENT_ALLOW_ORDER_SUBMISSION"):
        val = os.environ.get("VOLAGENT_ALLOW_ORDER_SUBMISSION", "false").lower() in ("true", "1", "yes")
        settings.execution.allow_order_submission = val
        settings.volagent_allow_order_submission = val

    return settings
