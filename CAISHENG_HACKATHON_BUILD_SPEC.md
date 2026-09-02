# CaiSheng

## Complete Hackathon Build Specification and Agent Handoff

**Target track:** Volatility & Event Trading Agents  
**Target broker and data platform:** Alpaca  
**Primary framework:** LangGraph  
**Primary interface:** Streamlit  
**Execution mode:** Alpaca paper trading only  
**Initial event type:** US-listed, after-market-close earnings announcements  
**Document status:** Authoritative implementation specification  
**Last updated:** 2026-08-22  

---

## 0. Instructions to the implementation agent

Build the system described in this document. Treat this document as the source of truth. Do not rely on the conversation that produced it.

When requirements appear to conflict, use this precedence order:

1. Safety, paper-only execution, and hard risk invariants.
2. Compliance with the competition track: the system must express a view on movement magnitude or implied volatility, never price direction.
3. A reliable five-minute judge demonstration.
4. Quantitative correctness and honest evaluation.
5. Alpaca and LangGraph integration.
6. Visual polish.
7. Stretch functionality.

Do not add speculative infrastructure or expand the strategy universe before every P0 acceptance criterion passes. Do not describe unfinished functionality as implemented. Do not invent historical results. Do not label synthetic or cached data as live data. Do not enable live-money trading.

Before writing code:

1. Inspect the repository and any `AGENTS.md` files.
2. Record the Python and package versions chosen.
3. Confirm the current Alpaca SDK, Alpaca MCP, and LangGraph APIs from official documentation.
4. Create a short implementation plan mapped to the milestones in this specification.
5. Preserve any pre-existing user files and changes.

After each milestone:

1. Run the milestone-specific tests.
2. Record failures and assumptions.
3. Do not proceed past a broken safety or mathematical invariant.

The intended result is **judge-grade**, not production-grade: narrow, rigorous, transparent, polished, and extremely reliable in a demonstration.

---

## 1. Product definition

### 1.1 One-sentence pitch

> CaiSheng is a multi-agent earnings-volatility desk that forecasts whether a stock will move more or less than its options market has priced, challenges that forecast with opposing volatility theses, selects a defined-risk delta-neutral structure, and executes an approved paper trade through Alpaca.

### 1.2 Track interpretation

The project must satisfy this track requirement literally:

> Build agents designed for earnings, macro events, or sudden volatility shifts, using options structures that express a view on movement itself or on implied volatility—rather than direction. Strong entries reason about IV, not just price.

Therefore:

- The system predicts unsigned movement, realized event variance, and post-event IV change.
- The system does not predict whether the stock will rise or fall.
- Event text is used to estimate uncertainty magnitude, novelty, dispersion, and event risk—not positive or negative price sentiment.
- No agent may recommend a standalone call, standalone put, bull spread, bear spread, or any structure selected because of expected direction.
- Every trade thesis must explicitly compare forecast movement or variance with option-implied movement or variance.
- Every trade thesis must explain gamma, theta, vega, and residual delta.
- `NO_TRADE` is a first-class, desirable outcome.

### 1.3 Primary user

The primary user is a hackathon judge. The judge must be able to understand and operate the application without reading the source code or entering API keys.

### 1.4 Winning qualities

The project should demonstrate five qualities visibly:

1. **Quantitative rigor:** a real event-move forecast, IV analysis, expected-value calculation, tail-risk constraints, and historical replay.
2. **Agentic depth:** specialized agents operate on different evidence, disagree through structured outputs, and can force abstention.
3. **Alpaca depth:** options data, account data, multi-leg paper orders, and preferably official MCP tool use.
4. **Transparency:** every number and claim has provenance; every rejection is explained.
5. **Demo reliability:** sealed replay scenarios and graceful fallbacks work outside market hours and without credentials.

### 1.5 Explicit non-goals

Do not implement these before the hackathon submission is complete:

- Live-money trading.
- Autonomous unattended execution.
- Directional equity or option trading.
- Naked short calls or puts.
- Reinforcement learning.
- High-frequency trading or dynamic intraday delta hedging.
- Continuous web-wide paper scraping.
- Runtime mining of hedge-fund or quant-firm websites.
- Social-media sentiment.
- A large strategy zoo.
- Support for every ticker, exchange, event type, and asset class.
- Full portfolio accounting, taxes, compliance, or regulatory suitability.
- Kubernetes, microservices, distributed queues, or other production infrastructure.
- Multiple frontend frameworks.
- Multiple LLM providers until the primary provider works reliably.
- Claims of production readiness or proven profitability.

### 1.6 Scope boundary

P0 scope is limited to:

- US equity and ETF options supported by Alpaca.
- Liquid underlyings from a configured allowlist.
- Earnings events occurring after the regular market close.
- One post-event expiration selected by deterministic rules.
- Three decisions: `LONG_STRADDLE`, `SHORT_IRON_BUTTERFLY`, or `NO_TRADE`.
- Paper trading only.
- Live analysis plus sealed historical replay.

Calendar spreads and scheduled macro events are P2 stretch work. They must not delay P0.

### 1.7 Assumptions that must be verified, not silently guessed

The official competition URL, final rubric, submission deadline, team-size rules, hosting constraints, and any supplied datasets were not provided when this specification was written. Before implementation, record them in `docs/competition-rules.md` from the official source. If an official rule conflicts with this specification, change only the affected requirement and document the reason.

Also verify:

- Whether Alpaca MCP use is required, merely encouraged, or unscored.
- Whether external paid data is permitted.
- Whether network access is available during judging.
- Whether judges will supply Alpaca credentials.
- Whether the submission must be hosted or only run locally.
- Maximum presentation time.
- Whether historical hypothetical performance may be displayed and what disclaimers are required.
- Whether generated AI explanations or model providers have disclosure requirements.

The build must remain functional in replay mode even when every answer above is unfavorable.

---

## 2. Judge-facing narrative

### 2.1 Problem statement

Most trading agents ask whether a stock will rise or fall. That is not the problem CaiSheng solves. Options encode a market-implied distribution. Around earnings, the key question is whether the magnitude of the move and the subsequent volatility repricing are correctly priced.

### 2.2 Central hypothesis

For earnings event \(e\):

\[
\text{Event Vol Edge}_e =
\text{Forecast Event Move}_e
- \text{Option-Implied Event Move}_e
- \text{Friction and Uncertainty Buffer}_e
\]

The sign and confidence of this edge determine whether the system should own volatility, sell volatility with defined risk, or abstain.

### 2.3 Judge-visible proof

The application must show all of the following for a selected scenario:

- What event is being analyzed and when it occurs.
- Whether the input is live, historical, cached-real, or synthetic.
- The current underlying and option quote timestamps.
- Implied move.
- Forecast median absolute move and uncertainty interval.
- Forecast post-event IV change.
- Long-vol and short-vol arguments with evidence IDs.
- Critic findings.
- Candidate strategies and why one won.
- Entry cost or credit, expected value after friction, maximum loss, Greeks, and stress losses.
- Risk-gate pass/fail results.
- Paper-order preview and receipt.
- Historical replay performance and baselines.

### 2.4 Five-minute demonstration script

The app must support this exact presentation:

**00:00–00:30 — Frame the problem**

Say: “Most trading agents predict direction. Options trade distributions. CaiSheng asks whether earnings movement and volatility are mispriced.”

**00:30–01:30 — Run a scenario**

Choose a sealed replay scenario with a clear but not absurd edge. Click `Run analysis`. Show the Event Evidence and Volatility Quant nodes executing in parallel.

**01:30–02:15 — Show disagreement**

Show one concise long-vol thesis, one short-vol thesis, and the Model-Risk Critic. Do not stream long token-by-token monologues.

**02:15–03:15 — Show the mathematical decision**

Display implied move, forecast distribution, IV-crush forecast, risk-adjusted expected value, Greeks, stress losses, and payoff diagram.

**03:15–03:45 — Show Alpaca integration**

Preview a multi-leg paper order. If credentials are configured, submit it after explicit approval and display the receipt. Otherwise, use a clearly labeled simulated paper receipt.

**03:45–04:30 — Show evidence beyond one event**

Open the Replay Scoreboard. Compare the full system with simple baselines. Show winning, losing, and no-trade examples.

**04:30–05:00 — Show restraint**

Run a stale-quote or illiquid scenario. The system must reject it. Finish with: “The system’s most important action is often refusing to trade when the volatility edge cannot survive uncertainty and execution costs.”

---

## 3. System architecture

### 3.1 Logical flow

```text
User selects ticker or replay scenario
                  |
                  v
        Input and mode validation
                  |
                  v
       Fetch point-in-time snapshot
                  |
        +---------+----------+
        |                    |
        v                    v
Event Magnitude Agent   Volatility Quant Agent
        |                    |
        +---------+----------+
                  |
                  v
      Deterministic Forecast Engine
                  |
        +---------+----------+
        |                    |
        v                    v
 Long-Vol Advocate     Short-Vol Advocate
        |                    |
        +---------+----------+
                  |
                  v
        Model-Risk Critic Agent
                  |
                  v
      Track Compliance Guard
                  |
                  v
   Deterministic Strategy Generator
                  |
                  v
      Monte Carlo Repricing Engine
                  |
                  v
   Deterministic Strategy Selector
                  |
                  v
      Deterministic Risk Gate
                  |
          +-------+-------+
          |               |
          v               v
       Reject       Human approval
                          |
                          v
            Alpaca paper-order adapter
                          |
                          v
          Execution receipt and audit log
```

### 3.2 Design principles

- LLM agents interpret and challenge evidence.
- Deterministic code owns market calculations, forecasts, strategy construction, risk, and order payloads.
- LLM output is always structured and schema-validated.
- LLM agents cannot call the order endpoint directly.
- Every graph node receives and returns typed state fragments.
- A node may fail closed but must not silently substitute fabricated data.
- Replay mode must be deterministic when the configured seed and model outputs are cached.
- The user must always see the data mode.

### 3.3 Inspiration and attribution

The system is architecturally inspired by Tauric Research’s TradingAgents:

- Parallel specialist analysts.
- Opposing research theses.
- A research manager or critic.
- Separation of research, trading, and risk.
- LangGraph conditional routing.
- Structured state, decision memory, and checkpointing.

The adaptation is substantive:

- Directional bull/bear research becomes long-vol/short-vol research.
- The target changes from signed return to absolute event movement and IV change.
- A deterministic forecast and option repricer sit between research and decision.
- A hard risk gate cannot be overridden by an LLM.
- Memory stores calibrated forecast errors and P&L attribution, not prose alone.

If any Tauric Research source code is copied or adapted, retain Apache-2.0 notices, include the upstream license, and document modified files in `NOTICE.md`. If only architectural ideas are used, cite the project and paper in the README.

---

## 4. Repository layout

Use this layout unless an existing repository requires a compatible variant:

```text
volagent-alpha/
├── README.md
├── NOTICE.md
├── LICENSE
├── pyproject.toml
├── uv.lock                         # or another committed lockfile
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile                     # optional but recommended reproducible demo
├── Makefile
├── app.py                          # Streamlit entry point
├── cli.py                          # deterministic local/replay CLI
├── docs/
│   ├── competition-rules.md
│   ├── methodology.md
│   ├── limitations.md
│   └── demo-script.md
├── config/
│   ├── default.yaml
│   ├── demo.yaml
│   └── risk_limits.yaml
├── data/
│   ├── README.md
│   ├── replay/
│   │   ├── manifest.json
│   │   ├── events.parquet
│   │   ├── option_quotes.parquet
│   │   ├── underlying_bars.parquet
│   │   ├── evidence.jsonl
│   │   └── scenario_results.jsonl
│   └── research/
│       └── evidence_cards.json
├── src/volagent/
│   ├── __init__.py
│   ├── config.py
│   ├── clock.py
│   ├── errors.py
│   ├── logging.py
│   ├── provenance.py
│   ├── domain/
│   │   ├── enums.py
│   │   ├── market.py
│   │   ├── events.py
│   │   ├── forecasts.py
│   │   ├── strategies.py
│   │   ├── risk.py
│   │   ├── execution.py
│   │   └── state.py
│   ├── data/
│   │   ├── ports.py
│   │   ├── alpaca_sdk.py
│   │   ├── alpaca_mcp.py
│   │   ├── replay.py
│   │   ├── earnings.py
│   │   ├── sec.py
│   │   ├── cache.py
│   │   └── normalization.py
│   ├── quant/
│   │   ├── conventions.py
│   │   ├── quote_filters.py
│   │   ├── pricing.py
│   │   ├── implied_vol.py
│   │   ├── greeks.py
│   │   ├── surface.py
│   │   ├── expected_move.py
│   │   ├── features.py
│   │   ├── forecast.py
│   │   ├── calibration.py
│   │   ├── scenarios.py
│   │   ├── repricing.py
│   │   ├── strategy_factory.py
│   │   ├── strategy_selector.py
│   │   ├── risk_gate.py
│   │   ├── payoff.py
│   │   └── attribution.py
│   ├── agents/
│   │   ├── prompts.py
│   │   ├── event_magnitude.py
│   │   ├── long_vol.py
│   │   ├── short_vol.py
│   │   ├── model_risk.py
│   │   ├── explainer.py
│   │   └── compliance.py
│   ├── graph/
│   │   ├── nodes.py
│   │   ├── routes.py
│   │   ├── builder.py
│   │   └── checkpoints.py
│   ├── execution/
│   │   ├── ports.py
│   │   ├── alpaca.py
│   │   ├── simulated.py
│   │   ├── approval.py
│   │   └── reconciliation.py
│   ├── evaluation/
│   │   ├── replay_runner.py
│   │   ├── baselines.py
│   │   ├── metrics.py
│   │   ├── ablations.py
│   │   └── reports.py
│   └── ui/
│       ├── theme.py
│       ├── state.py
│       ├── components.py
│       ├── charts.py
│       └── pages/
│           ├── analyze.py
│           ├── decision.py
│           ├── scoreboard.py
│           └── audit.py
├── scripts/
│   ├── build_replay_dataset.py
│   ├── train_forecasters.py
│   ├── validate_replay_manifest.py
│   ├── precompute_demo_runs.py
│   └── smoke_test_alpaca.py
└── tests/
    ├── unit/
    ├── property/
    ├── integration/
    ├── graph/
    ├── replay/
    ├── ui/
    └── fixtures/
```

---

## 5. Runtime and dependencies

### 5.1 Runtime

- Python 3.12.
- Use `uv` for environment and lockfile management if available; otherwise use a committed, hashed requirements lock.
- Use UTC internally.
- Convert market times explicitly with `zoneinfo.ZoneInfo("America/New_York")`.
- Never use naive datetimes in domain models.

### 5.2 Required packages

Pin exact compatible versions in the lockfile after verifying current APIs:

- `langgraph`
- `pydantic`
- `pydantic-settings`
- `alpaca-py`
- official Alpaca MCP server/client dependencies if MCP is implemented
- `streamlit`
- `plotly`
- `numpy`
- `pandas`
- `scipy`
- `scikit-learn`
- `pyarrow`
- `duckdb`
- `httpx`
- `tenacity`
- `structlog`
- `PyYAML`
- `joblib`
- `typer`
- `pytest`
- `pytest-cov`
- `hypothesis`
- `ruff`
- `mypy`

Avoid adding a vector database. The curated evidence collection is small and can use JSON plus simple lexical or embedding retrieval only if already available.

### 5.3 Configuration and secrets

`.env.example` must contain names only, never values:

```dotenv
VOLAGENT_ENV=demo
VOLAGENT_LOG_LEVEL=INFO
VOLAGENT_DATA_MODE=replay
VOLAGENT_RANDOM_SEED=20260822
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER_TRADE=true
ALPACA_DATA_FEED=indicative
VOLAGENT_ALLOW_ORDER_SUBMISSION=false
VOLAGENT_REPLAY_SCENARIO_ID=
```

Rules:

- `ALPACA_PAPER_TRADE` must default to `true` and application startup must fail if set to `false`.
- `VOLAGENT_ALLOW_ORDER_SUBMISSION` defaults to `false`.
- Even when order submission is enabled, only paper endpoints are permitted.
- Secrets must never appear in logs, UI, graph state, replay files, traces, or exception messages.
- Demo mode must start without any API keys.

### 5.4 Default configuration

`config/default.yaml`:

```yaml
application:
  name: CaiSheng
  timezone: America/New_York
  random_seed: 20260822
  max_graph_runtime_seconds: 90
  llm_timeout_seconds: 20
  llm_retries: 1
  cache_ttl_seconds: 60

universe:
  symbols: [AAPL, AMD, AMZN, GOOGL, META, MSFT, NFLX, NVDA, TSLA]
  require_after_market_close_event: true

contracts:
  min_days_after_event: 2
  max_days_after_event: 14
  min_open_interest: 100
  min_daily_volume: 10
  min_mid_price: 0.10
  max_relative_spread: 0.15
  max_quote_age_seconds: 60
  max_atm_distance_pct: 0.03

forecast:
  quantiles: [0.20, 0.50, 0.80]
  min_training_events: 80
  min_ticker_events_for_ticker_component: 6
  monte_carlo_scenarios: 3000
  confidence_floor: 0.60
  edge_buffer_pct_spot: 0.0025

risk:
  recommended_risk_nav_pct: 0.005
  hard_max_risk_nav_pct: 0.01
  max_abs_dollar_delta_nav_pct: 0.02
  max_stress_loss_nav_pct: 0.01
  max_contracts: 10
  require_defined_risk_for_short_vol: true
  reject_dividend_before_expiry: true

execution:
  paper_only: true
  require_human_approval: true
  order_type: limit
  time_in_force: day
  limit_improvement_fraction: 0.25
  fee_per_contract: 0.05
  slippage_per_contract: 0.02
```

All thresholds must be displayed in the Audit page and overridable only through configuration, not through LLM output.

---

## 6. Domain model and typed contracts

All domain models must be immutable or treated as immutable after validation. Use Pydantic models with `extra="forbid"`.

### 6.1 Core enums

```python
class DataMode(str, Enum):
    LIVE = "live"
    HISTORICAL = "historical"
    REPLAY_REAL = "replay_real"
    REPLAY_SYNTHETIC = "replay_synthetic"

class EventTiming(str, Enum):
    BEFORE_MARKET_OPEN = "bmo"
    AFTER_MARKET_CLOSE = "amc"
    DURING_MARKET = "during_market"
    UNKNOWN = "unknown"

class Decision(str, Enum):
    LONG_STRADDLE = "long_straddle"
    SHORT_IRON_BUTTERFLY = "short_iron_butterfly"
    NO_TRADE = "no_trade"

class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"

class RunStatus(str, Enum):
    CREATED = "created"
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    REJECTED = "rejected"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 6.2 Provenance record

Every external fact must carry:

```python
class Provenance(BaseModel):
    source_name: str
    source_uri: str | None
    retrieved_at: datetime
    observed_at: datetime
    effective_at: datetime | None
    content_hash: str
    data_mode: DataMode
```

Definitions:

- `retrieved_at`: when VolAgent fetched the record.
- `observed_at`: when the information became available to a market participant.
- `effective_at`: when the event or value applies.
- `content_hash`: SHA-256 of the normalized source payload.

Reject historical inputs whose `observed_at` occurs after the simulated decision time.

### 6.3 Market and event models

Required models:

```python
class UnderlyingSnapshot(BaseModel):
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    quote_time: datetime
    previous_close: float | None
    realized_vol_10d: float | None
    realized_vol_30d: float | None
    provenance: Provenance

class OptionContractSnapshot(BaseModel):
    symbol: str
    underlying_symbol: str
    option_type: Literal["call", "put"]
    strike: float
    expiration: date
    bid: float
    ask: float
    last: float | None
    quote_time: datetime
    volume: int | None
    open_interest: int | None
    vendor_implied_vol: float | None
    vendor_delta: float | None
    vendor_gamma: float | None
    vendor_theta: float | None
    vendor_vega: float | None
    multiplier: int = 100
    provenance: Provenance

class EarningsEvent(BaseModel):
    event_id: str
    symbol: str
    fiscal_period: str | None
    event_time: datetime
    timing: EventTiming
    confirmed: bool
    decision_time: datetime
    exit_time: datetime
    provenance: Provenance

class EvidenceItem(BaseModel):
    evidence_id: str
    category: Literal[
        "filing", "earnings_history", "guidance_uncertainty",
        "analyst_dispersion", "news_novelty", "macro_context",
        "market_data", "option_surface"
    ]
    claim: str
    magnitude_relevance: str
    numeric_value: float | None
    units: str | None
    confidence: float
    provenance: Provenance
```

### 6.4 Forecast models

```python
class MoveForecast(BaseModel):
    median_abs_move_pct: float
    q20_abs_move_pct: float
    q80_abs_move_pct: float
    probability_exceeds_implied: float
    implied_move_pct: float
    edge_pct_spot: float
    uncertainty_buffer_pct_spot: float
    calibration_confidence: float
    out_of_distribution: bool
    model_version: str
    feature_snapshot_hash: str

class IVCrushForecast(BaseModel):
    median_iv_change_points: float
    q20_iv_change_points: float
    q80_iv_change_points: float
    model_version: str
    calibration_confidence: float
```

All percentages are decimal fractions internally. For example, 7.8% is stored as `0.078`. UI formatting converts to percent.

### 6.5 Agent output contracts

```python
class VolatilityThesis(BaseModel):
    side: Literal["long_vol", "short_vol"]
    directional_view: Literal["none"]
    thesis: str
    numeric_argument: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    invalidation_conditions: list[str]
    confidence: float

class CriticReport(BaseModel):
    status: GateStatus
    directional_leakage_detected: bool
    temporal_leakage_detected: bool
    stale_data_detected: bool
    excessive_model_disagreement: bool
    unsupported_claim_ids: list[str]
    failure_reasons: list[str]
    warnings: list[str]
    recommendation: Literal["continue", "force_no_trade"]
```

Confidence is restricted to `[0, 1]`. Empty evidence lists are invalid for a positive thesis.

### 6.6 Strategy and execution contracts

```python
class OptionLeg(BaseModel):
    contract_symbol: str
    option_type: Literal["call", "put"]
    strike: float
    expiration: date
    side: Literal["buy", "sell"]
    position_intent: Literal[
        "buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"
    ]
    ratio_qty: int
    entry_price_assumption: float
    delta: float
    gamma: float
    theta: float
    vega: float

class StrategyCandidate(BaseModel):
    strategy_id: str
    decision: Decision
    legs: list[OptionLeg]
    quantity: int
    entry_debit_credit: float
    max_profit: float | None
    max_loss: float
    break_evens: list[float]
    expected_pnl: float
    expected_shortfall_95: float
    probability_of_profit_model: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    stress_losses: dict[str, float]
    liquidity_score: float
    risk_adjusted_score: float

class RiskCheck(BaseModel):
    name: str
    status: GateStatus
    observed: str
    limit: str
    explanation: str

class RiskReport(BaseModel):
    overall_status: GateStatus
    checks: list[RiskCheck]
    approved_quantity: int
    rejection_reasons: list[str]

class OrderPlan(BaseModel):
    client_order_id: str
    strategy_id: str
    paper_only: Literal[True]
    order_class: Literal["mleg"]
    order_type: Literal["limit"]
    time_in_force: Literal["day"]
    quantity: int
    limit_price: float
    legs: list[OptionLeg]
    expires_at: datetime
    fingerprint: str

class ExecutionReceipt(BaseModel):
    broker: Literal["alpaca", "simulated"]
    paper: Literal[True]
    order_id: str
    client_order_id: str
    status: str
    submitted_at: datetime
    raw_response_hash: str
```

### 6.7 LangGraph state

`VolAgentState` must contain references to artifacts, not API clients or secrets:

```python
class VolAgentState(TypedDict, total=False):
    run_id: str
    status: RunStatus
    mode: DataMode
    symbol: str
    event: EarningsEvent
    underlying: UnderlyingSnapshot
    option_chain: list[OptionContractSnapshot]
    evidence: list[EvidenceItem]
    feature_set: dict[str, float | int | bool | None]
    move_forecast: MoveForecast
    iv_forecast: IVCrushForecast
    long_vol_thesis: VolatilityThesis
    short_vol_thesis: VolatilityThesis
    critic_report: CriticReport
    candidates: list[StrategyCandidate]
    selected_candidate: StrategyCandidate | None
    risk_report: RiskReport
    order_plan: OrderPlan | None
    execution_receipt: ExecutionReceipt | None
    rejection_reasons: list[str]
    trace_events: list[dict[str, Any]]
    artifact_hashes: dict[str, str]
```

Never store full raw filings, full news articles, API keys, or large option histories in graph state.

### 6.8 Monetary, payoff, and Greek sign conventions

Use these conventions everywhere:

- Dollar P&L is positive for profit and negative for loss.
- `max_loss` and `expected_shortfall_95` are stored as positive loss magnitudes.
- `stress_losses` are stored as positive loss magnitudes; a profitable stress point has loss `0`, with its profit available separately if needed.
- `entry_debit_credit` is negative for a debit paid and positive for a credit received.
- `expected_pnl` is net dollars for the complete configured position quantity.
- `probability_of_profit_model` is in `[0,1]` and refers to net P&L after the configured friction model.
- Option vendor Greeks are normalized to the exposure of one long option contract before strategy aggregation.
- Buy legs have exposure sign `+1`; sell legs have exposure sign `-1`.
- Aggregated dollar Greeks include leg ratio, strategy quantity, multiplier, and side sign.
- UI labels must explicitly say `Debit`, `Credit`, `Profit`, or `Loss`; do not expose an ambiguous signed field name to judges.

Add tests proving these conventions for both candidate strategies.

---

## 7. Data modes and source behavior

### 7.1 Mode definitions

**Live:** Current Alpaca data and a future confirmed earnings event. Order submission may be available, but paper-only and approval-gated.

**Historical:** A point-in-time historical analysis assembled from provider data. It must enforce the decision timestamp.

**Replay Real:** A sealed scenario generated from real historical data with hashes and provenance. This is the default demo mode.

**Replay Synthetic:** A synthetic failure or stress scenario. It may demonstrate behavior but may never contribute to performance claims.

### 7.2 Data-source priority

1. Official Alpaca MCP or Alpaca SDK for current market, option, account, news, and paper-order data.
2. Official SEC EDGAR APIs for filings.
3. A confirmed earnings-calendar source available through the competition environment or a curated replay record.
4. Sealed replay artifacts.

Do not scrape Cboe delayed quote pages or any site whose terms prohibit automation.

### 7.3 Alpaca integration ports

Define these interfaces:

```python
class MarketDataPort(Protocol):
    def get_underlying_snapshot(self, symbol: str) -> UnderlyingSnapshot: ...
    def get_option_chain(
        self, symbol: str, as_of: datetime | None = None
    ) -> list[OptionContractSnapshot]: ...
    def get_underlying_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> pd.DataFrame: ...
    def get_news(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[EvidenceItem]: ...

class AccountPort(Protocol):
    def get_paper_account_equity(self) -> float: ...
    def get_positions(self) -> list[dict[str, Any]]: ...

class ExecutionPort(Protocol):
    def preview(self, plan: OrderPlan) -> dict[str, Any]: ...
    def submit_paper_order(self, plan: OrderPlan) -> ExecutionReceipt: ...
```

Implement SDK and replay ports first. Implement MCP behind the same interfaces. The UI should show which adapter supplied each artifact.

### 7.4 MCP behavior

When official Alpaca MCP is enabled:

- Start or connect to the official MCP server according to current official documentation.
- Discover the current tool schemas rather than assuming stale parameter names.
- Restrict enabled toolsets to the minimum required: account, trading, options data, stock data, assets, and news.
- Normalize MCP results into the same Pydantic domain models used by the SDK adapter.
- Record the tool name, invocation time, response hash, latency, and success/failure—not secrets or full sensitive payloads.
- Never allow a free-form LLM to call `place_option_order` directly. Only the deterministic execution node may invoke it with a validated `OrderPlan`.

### 7.5 Snapshot consistency

For a live run:

- Fetch the underlying snapshot first.
- Fetch the option chain immediately afterward.
- Reject if the oldest required quote is older than `max_quote_age_seconds`.
- Reject if underlying and option snapshots differ by more than 90 seconds.
- Stamp one `snapshot_cutoff` equal to the earliest latest-safe time across inputs.
- Every feature must be computed only from data observed by that cutoff.

### 7.6 Earnings-event validation

P0 accepts only events meeting all conditions:

- Symbol is in the configured allowlist.
- Event timestamp is confirmed.
- Timing is `AFTER_MARKET_CLOSE`.
- Event occurs after the decision timestamp.
- The selected option expiration occurs after the event.
- No known ex-dividend date falls between entry and expiration when `reject_dividend_before_expiry` is true.
- The event has not already been incorporated into a previous open VolAgent position.

Unknown or conflicting event times force `NO_TRADE`.

---

## 8. Market conventions and quote filtering

### 8.1 Internal conventions

- Prices are USD per share unless explicitly labeled per contract.
- Option P&L multiplies per-share option prices by the contract multiplier, normally 100.
- Volatility is stored as an annualized decimal, such as `0.45` for 45%.
- Vega must document whether it represents a one-point or one-unit volatility change. Normalize internal vega to dollars per one volatility point.
- Rates and dividend yields are decimals.
- Time to expiry uses actual seconds divided by 365.25 days for consistency. Document this choice.
- Use the option expiration settlement time applicable to the contract. For P0 equity options, default to regular Friday close only after checking contract metadata.

### 8.2 Basic quote calculations

For bid \(b\) and ask \(a\):

\[
m = \frac{a+b}{2}
\]

\[
\text{relative spread} = \frac{a-b}{m}
\]

Reject a quote when:

- `bid < 0` or `ask <= 0`.
- `ask < bid`.
- `mid < min_mid_price`.
- Relative spread exceeds the configured maximum.
- Quote age exceeds the configured maximum.
- Open interest is absent or below the configured minimum.
- Volume is absent or below the configured minimum unless replay metadata explicitly marks volume unavailable and the scenario is not used for execution.
- Contract multiplier is unsupported.

### 8.3 Conservative fill assumptions

Never backtest at the midpoint by default.

- Long entry: buy at ask plus configured slippage.
- Long exit: sell at bid minus configured slippage.
- Short entry: sell at bid minus configured slippage.
- Short exit: buy at ask plus configured slippage.
- Add per-contract fees on entry and exit.
- For a multi-leg live limit order, compute a natural debit/credit and a midpoint. Start the limit a configured fraction from natural toward midpoint; do not automatically cross beyond the configured maximum.

### 8.4 Contract universe filter order

Apply filters in this order and log counts after each stage:

1. Correct underlying.
2. Correct expiration window.
3. Standard contract multiplier.
4. Valid call/put type and strike.
5. Fresh quote.
6. Non-crossed positive market.
7. Minimum mid.
8. Maximum spread.
9. Minimum open interest.
10. Minimum volume.
11. Strike within configured distance of spot or required wing range.
12. No corporate-action or adjusted contract flag unless explicitly supported.

If fewer than the required legs remain, force `NO_TRADE`.

---

## 9. Mathematical specification

### 9.1 The target is unsigned movement

For event \(e\), define the realized absolute log move from the last regular-session price before earnings to the first configured post-event observation:

\[
Y_e = \left|\log\left(\frac{S_{e,\text{exit}}}{S_{e,\text{entry}}}\right)\right|
\]

P0 replay convention:

- Entry time: 15:45 America/New_York on the final regular session before an after-close earnings announcement.
- Exit observation: 10:00 America/New_York on the next regular session.
- If either timestamp lacks a valid quote or bar, the event is excluded with a recorded reason.

Never use the signed return as a predictive target.

### 9.2 Realized volatility features

Compute close-to-close realized volatility over \(n\) sessions:

\[
\sigma_{RV,n} = \sqrt{252}\;\operatorname{std}(r_{t-n+1},\ldots,r_t)
\]

where \(r_t=\log(S_t/S_{t-1})\).

At minimum compute 10-day and 30-day realized volatility. Do not call `IV - RV30` an event volatility risk premium unless horizons are aligned; label it `iv_minus_recent_rv` in features.

### 9.3 ATM selection

Estimate the forward:

\[
F = S e^{(r-q)T}
\]

Select the strike minimizing \(|K-F|\) among strikes with both a valid call and put. If rates or dividend yield are unavailable, use spot for selection and mark the approximation.

Reject if the selected strike differs from spot by more than `max_atm_distance_pct`.

### 9.4 Implied move

For the selected ATM call and put:

\[
M_{mid} = \frac{C_{mid}+P_{mid}}{S}
\]

Also compute executable bounds:

\[
M_{long-entry} = \frac{C_{ask}+P_{ask}}{S}
\]

\[
M_{short-entry} = \frac{C_{bid}+P_{bid}}{S}
\]

Display `M_mid` as the headline market-implied move, but use executable prices in expected-value calculations. Explain that the straddle cost is a market breakeven heuristic, not a guaranteed expected move.

### 9.5 Option pricing and IV inversion

Use Black–Scholes–Merton for consistency checks and scenario repricing:

\[
C = Se^{-qT}N(d_1)-Ke^{-rT}N(d_2)
\]

\[
P = Ke^{-rT}N(-d_2)-Se^{-qT}N(-d_1)
\]

\[
d_1=\frac{\ln(S/K)+(r-q+\frac{1}{2}\sigma^2)T}{\sigma\sqrt{T}},
\qquad d_2=d_1-\sigma\sqrt{T}
\]

Invert IV with Brent’s method over a documented range such as `[1e-4, 5.0]`. Fail rather than returning a fabricated IV when the price violates bounds or no root exists.

US equity options are American-style. For P0:

- Use vendor IV and Greeks as primary current values when present.
- Use BSM as a cross-check and scenario approximation.
- Reject contracts spanning an ex-dividend date by default.
- State the approximation in the UI Audit page.
- Bjerksund–Stensland is P2 and must not delay the build.

### 9.6 No-arbitrage surface checks

For filtered quotes, flag:

- Call prices materially increasing with strike.
- Put prices materially decreasing with strike.
- Butterfly convexity violations beyond a tolerance.
- Calendar total-variance inversions beyond a tolerance.
- Vendor IV discontinuities far beyond neighboring strikes.

Do not attempt a complete arbitrage-free surface calibration in P0. Produce a `surface_quality_score` in `[0,1]` and force `NO_TRADE` below a configured threshold.

### 9.7 Event variance from term structure

For ATM total implied variance:

\[
w(T)=\sigma_{ATM}^2(T)T
\]

Fit a simple baseline through non-event expirations or adjacent maturities. Estimate event variance as non-negative excess total variance in the first expiration spanning the event:

\[
v_{event,imp}=\max(0,w(T_{post})-\widehat{w}_{baseline}(T_{post}))
\]

Report this as a secondary diagnostic. The primary P0 implied-move measure remains the executable ATM straddle because it is easier to explain and less fragile with sparse chains.

### 9.8 Forecast targets

Train separate models for:

1. Absolute event move `abs_log_move`.
2. Post-event ATM IV change in volatility points:

\[
\Delta IV_e = 100(IV_{after}-IV_{before})
\]

Use quantile regression for 20th, 50th, and 80th percentiles.

For `probability_exceeds_implied`, train a separate chronologically validated probabilistic classifier on:

\[
Z_e=\mathbf{1}[Y_e > M_{implied,e}]
\]

Calibrate it on the validation period using isotonic or Platt calibration only when sample size is adequate. If the classifier cannot be trained or calibrated credibly, estimate exceedance frequency from the forecast scenario distribution and label it `scenario-derived, uncalibrated`; do not display the word `calibrated`.

### 9.9 Forecast features

The P0 feature vector may include only values available by the decision timestamp:

- Implied move at mid and executable long/short bounds.
- ATM IV.
- IV term slope.
- 25-delta or nearest-available put/call skew.
- Surface curvature proxy.
- Event implied-variance excess.
- Relative bid-ask spread.
- Open interest and volume aggregates.
- 10-day and 30-day realized volatility.
- Ratio of implied move to ticker historical median earnings move.
- Median and dispersion of the ticker’s prior earnings moves.
- Sector historical event-move median and dispersion.
- Broad-market volatility regime if point-in-time data exists.
- Days to expiration.
- Event novelty, guidance uncertainty, and analyst-dispersion scores from the Event Magnitude Agent, each bounded to `[0,1]`.
- Missingness flags for every optional feature.

Forbidden features:

- Actual earnings result or surprise from the current event.
- Post-event price, IV, volume, news, or filings.
- Current-day data revisions that were unavailable historically.
- Signed sentiment or expected direction.
- Future earnings dates as known today when simulating past events.

### 9.10 Baseline forecaster

Always implement a deterministic shrinkage baseline before machine learning:

\[
\hat m = w_t m_{ticker}+w_s m_{sector}+w_g m_{global}
\]

Weights increase with available historical observations and must sum to one. Use only prior events. If ticker history is sparse, shrink more heavily toward sector and global medians.

Estimate uncertainty from historical residual quantiles. This baseline is both a fallback and an evaluation comparator.

### 9.11 Quantile model

Use three `GradientBoostingRegressor(loss="quantile")` models or an equivalently simple, auditable implementation for \(\tau=0.2,0.5,0.8\).

Requirements:

- Train only on events earlier than the evaluation period.
- Use expanding-window or rolling walk-forward validation.
- Tune very few hyperparameters.
- Save feature names, training cutoff, data hash, code version, and model parameters with each artifact.
- Correct quantile crossing by sorting predicted quantiles if necessary and record how often this occurs.
- Use out-of-distribution detection based on feature ranges or robust distance. OOD forecasts reduce confidence or force abstention.

If fewer than `min_training_events` eligible historical events exist, do not train or display a machine-learning model. Use the deterministic shrinkage baseline, widen its empirical uncertainty interval, label the forecast `historical shrinkage baseline`, and retain `NO_TRADE` when its interval does not produce a robust edge.

LLM-derived event features may enter a trained model only when equivalent point-in-time evidence was available and processed for historical training events with the same prompt/schema version. Otherwise, show the Event Magnitude assessment as qualitative supporting evidence only and exclude its scores from the numerical feature vector.

### 9.12 Forecast calibration

Use held-out residuals to calibrate intervals. Report:

- Pinball loss per quantile.
- Empirical coverage of the 20–80 interval.
- Mean absolute error of the median forecast.
- CRPS when implemented correctly.
- Reliability of `P(move > implied)` buckets.

The UI must not display an uncalibrated confidence value as a probability.

### 9.13 Scenario generation

Generate at least 3,000 deterministic Monte Carlo scenarios using the configured seed.

For each scenario:

1. Draw absolute move magnitude from the calibrated forecast distribution.
2. Assign positive or negative sign with equal probability to avoid a directional view.
3. Draw post-event IV change from the calibrated IV forecast.
4. Apply the move to the forward or spot consistently.
5. Reprice every candidate leg at the configured exit time.
6. Apply conservative exit prices, slippage, and fees.

The equal-sign assumption must be displayed. If later research models skew, it may affect risk analysis but may not be used to choose directional structures in this track.

### 9.14 Strategy expected value

For strategy \(s\):

\[
EV_s = \mathbb{E}_P[V_{s,exit}] - V_{s,entry} - Costs_s
\]

Compute:

- Expected P&L.
- Median P&L.
- Probability of positive P&L under the forecast model.
- 5th percentile P&L.
- Expected shortfall at 95%.
- Maximum contractual loss.

Label probability of profit as **model probability**, never as a market fact.

### 9.15 Risk-adjusted score

Use:

\[
Score_s = EV_s - \lambda |ES_{95,s}| - Penalty_{liquidity} - Penalty_{uncertainty}
\]

Keep \(\lambda\) configurable and fixed during evaluation. Do not tune it on the final replay set.

### 9.16 Greeks and P&L attribution

Aggregate leg Greeks with quantity, side, and multiplier. Normalize vega to dollars per one IV point.

Approximate change:

\[
dV\approx \Delta dS+\frac{1}{2}\Gamma(dS)^2+Vega\,d\sigma+\Theta dt+\epsilon
\]

Report:

- Delta contribution.
- Gamma or movement contribution.
- Vega or IV-change contribution.
- Theta contribution.
- Residual.

The expected delta contribution should be close to zero. Large directional contribution is a compliance warning and may force `NO_TRADE`.

---

## 10. Strategy construction

### 10.1 General rules

The strategy generator is deterministic. It receives a clean option chain, forecasts, account equity, and configuration. It may generate only supported structures. It must never ask an LLM to choose arbitrary strikes or formulate an order payload.

Every generated candidate must:

- Use contracts on the same underlying.
- Use one expiration in P0.
- Express movement or volatility, not direction.
- Satisfy quote-quality requirements for every leg.
- Have approximately neutral entry delta.
- Have a calculable maximum loss.
- Be representable as one Alpaca multi-leg order.
- Use whole-number contract ratios supported by Alpaca.

### 10.2 Expiration selection

For an after-close earnings event, select the nearest expiration satisfying:

- Expiration is strictly after the event.
- At least `min_days_after_event` calendar days remain after the event.
- No more than `max_days_after_event` calendar days remain after the event.
- The ATM call and put pass all liquidity filters.

If multiple expirations qualify, rank by:

1. Lowest combined relative spread.
2. Highest combined open interest.
3. Shortest time after the event.

If none qualify, return no candidates.

### 10.3 Long ATM straddle

Legs:

- Buy one ATM call.
- Buy one ATM put.
- Same strike and expiration.

Entry debit per spread unit:

\[
D = 100(C_{ask}+P_{ask}) + Fees + Slippage
\]

Maximum loss is the total debit. Break-evens at expiration are approximately:

\[
K-D/100, \qquad K+D/100
\]

The entry must be rejected when:

- Net absolute dollar delta exceeds the configured limit.
- Total debit exceeds hard risk budget even at one contract.
- Either leg fails liquidity filters.
- Forecast edge does not exceed the uncertainty and friction buffer.
- The model predicts severe IV crush and insufficient movement to compensate.

### 10.4 Short defined-risk iron butterfly

Legs:

- Sell one ATM call.
- Sell one ATM put.
- Buy one OTM call wing.
- Buy one OTM put wing.
- Same expiration.

Wing selection:

1. Start with strikes nearest `ATM strike ± implied move in dollars`.
2. Search outward and inward over valid strikes.
3. Prefer approximately symmetric wing widths.
4. Require every leg to satisfy filters.
5. Calculate exact contractual maximum loss for asymmetric wings.
6. Reject if net delta or stress loss exceeds limits.

Entry credit uses executable bid for shorts and ask for longs, minus fees and slippage.

For symmetric wing width \(W\) and net credit \(C\) per share:

\[
MaxLoss \approx 100(W-C)
\]

Use exact leg payoff for the implementation, not only this approximation.

Never create a naked short straddle or strangle. Never omit protective wings because of missing or illiquid quotes.

### 10.5 No trade

Return `NO_TRADE` whenever any of these apply:

- Critic forces abstention.
- No candidate passes risk.
- All candidate risk-adjusted scores are non-positive.
- Difference between the top two scores is smaller than the configured decision margin.
- Forecast confidence is below the floor.
- Forecast is out of distribution.
- Surface quality is inadequate.
- Event time is unconfirmed or not after close.
- Required quotes are stale, wide, crossed, or missing.
- Data modes are mixed inconsistently.
- Directional leakage is detected.
- Account equity is unavailable for a live order.
- Paper order cannot be expressed as one supported multi-leg order.

No-trade output must list the exact checks that failed and what evidence would be required to reconsider.

### 10.6 Quantity sizing

Define risk budget:

\[
B = NAV \times risk\_nav\_pct
\]

For long straddles:

\[
q = \left\lfloor \frac{B}{DebitPerUnit} \right\rfloor
\]

For iron butterflies:

\[
q = \left\lfloor \frac{B}{MaxLossPerUnit} \right\rfloor
\]

Then cap by `max_contracts`, broker buying power, and any stricter stress limit. A zero quantity forces `NO_TRADE`.

### 10.7 Limit-price construction

For each multi-leg order compute:

- Natural debit or credit from executable side prices.
- Midpoint debit or credit from leg midpoints.
- A proposed limit price between natural and midpoint using `limit_improvement_fraction`.

Round to the broker-permitted increment. Recompute max loss using the proposed limit. Never submit a market multi-leg order.

### 10.8 P2 calendar spread

Only after P0 passes, optionally support a delta-neutral ATM calendar:

- Sell the nearer expiration.
- Buy the farther expiration.
- Same strike and option type pair constructed as a double calendar if needed to remain direction-neutral.
- Thesis must be a term-structure mispricing or differential IV crush.

Do not implement a one-sided call or put calendar for P0 because it introduces directional exposure and complicates the track narrative.

---

## 11. Deterministic risk gate

### 11.1 Authority

The risk gate is final. No LLM agent, user prompt, or UI control may override a failed hard check. Changing a hard limit requires editing configuration and restarting the run.

### 11.2 Required hard checks

Implement each check separately and return a `RiskCheck`:

1. **Paper-only endpoint:** execution adapter proves it targets an Alpaca paper endpoint or the simulated adapter.
2. **Supported decision:** only long straddle, short iron butterfly, or no trade.
3. **Defined risk:** every short option is covered by a valid long wing in the same order.
4. **Maximum loss:** total maximum loss is at most `hard_max_risk_nav_pct × NAV`.
5. **Recommended risk:** warn if risk exceeds the recommended budget but fail only at the hard cap.
6. **Delta neutrality:** absolute dollar delta divided by NAV is within the configured maximum.
7. **Quote freshness:** all legs pass freshness.
8. **Spread:** all legs pass relative-spread threshold.
9. **Liquidity:** all legs pass volume and open-interest thresholds.
10. **Event validity:** confirmed AMC earnings event after decision time.
11. **Expiration validity:** expiration is after event and inside configured window.
12. **Corporate action:** no unsupported adjusted contract or ex-dividend exposure.
13. **Stress loss:** worst configured stress loss is within cap.
14. **Order integrity:** all legs share underlying and valid expiration; ratios are positive whole numbers.
15. **Directional compliance:** structure is not a standalone call/put or directional vertical.
16. **Model confidence:** forecast confidence meets floor and is not OOD.
17. **Critic approval:** critic did not force no trade.
18. **Data consistency:** no live/replay mixing and all provenance precedes decision time.
19. **Duplicate protection:** order fingerprint has not already been approved or submitted.
20. **Approval freshness:** approval has not expired.

### 11.3 Dollar delta

For legs \(i\):

\[
DollarDelta = S \sum_i q_i \times multiplier_i \times \Delta_i
\]

Use side signs consistently. Report:

\[
DeltaNAV = |DollarDelta|/NAV
\]

### 11.4 Stress grid

At minimum reprice the structure under:

- Underlying move: `{-2M, -M, 0, +M, +2M}`, where \(M\) is implied move.
- IV change in points: `{-20, -10, 0, +10, +20}` with a floor above zero.
- Exit times: immediate post-event and configured exit time.

Report the worst scenario and a heatmap. Contractual max loss remains the authoritative cap for defined-risk expiry payoff.

### 11.5 Approval fingerprint

Create a SHA-256 fingerprint over canonical JSON containing:

- Account identifier hash, not raw account number.
- Run ID.
- Symbol.
- Strategy ID.
- Quantity.
- Limit price.
- Every leg symbol, side, ratio, and position intent.
- Paper endpoint identifier.
- Expiration timestamp of approval.

The approval token applies only to this fingerprint and may be used once.

---

## 12. Agents and exact behavior

### 12.1 Shared LLM rules

All LLM agents must:

- Use temperature zero or the provider’s most deterministic supported mode.
- Produce one schema-validated structured response.
- Receive only necessary compact artifacts.
- Cite evidence IDs for factual claims.
- Distinguish facts, calculations, assumptions, and opinions.
- Never invent prices, Greeks, dates, filings, quotes, or performance.
- Never predict up versus down.
- Never recommend a standalone call or put.
- Never formulate broker JSON.
- Never override deterministic calculations or risk failures.
- Say evidence is insufficient when it is insufficient.
- Complete within the configured timeout.

One retry is allowed for invalid JSON or transient provider failure. On repeated failure, the graph must either use a clearly labeled cached agent output in replay mode or force `NO_TRADE`.

### 12.2 Event Magnitude Agent

Purpose: convert point-in-time filings, news, event history, and analyst-dispersion evidence into bounded features describing uncertainty magnitude.

It must not determine trade direction or final strategy.

System prompt:

```text
You are the Event Magnitude Analyst for an earnings-volatility desk.

Your task is to assess how unusual and uncertain the upcoming earnings event may be. You predict neither an upward nor a downward price move. Do not use bullish, bearish, upside, downside, buy, sell, call, or put recommendations.

Use only the supplied evidence items. Every factual claim must cite one or more evidence_id values. Separate event magnitude from direction. A large positive surprise and a large negative surprise are equivalent for your purpose: both may create a large absolute move.

Return only the requested structured object. Scores must be between 0 and 1. If evidence is missing or conflicting, reduce confidence and state the conflict. Do not invent values.
```

Expected output:

```python
class EventMagnitudeAssessment(BaseModel):
    directional_view: Literal["none"]
    event_novelty_score: float
    guidance_uncertainty_score: float
    analyst_dispersion_score: float
    magnitude_pressure_score: float
    confidence: float
    supporting_evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    summary: str
    missing_information: list[str]
```

The deterministic feature builder clips values to `[0,1]` and adds missingness flags. The model may use the scores only if the assessment passes evidence validation.

### 12.3 Volatility Quant Agent

This is a deterministic node presented as an agent in the UI. It computes:

- Quote-filter audit.
- Selected expiration and ATM strike.
- ATM IV and vendor/computed IV difference.
- Implied-move measures.
- Term slope, skew, curvature, and surface quality.
- Realized-volatility features.
- Liquidity score.
- Greeks and timestamp checks.

It produces no natural-language trade recommendation. Its output is reproducible from the snapshot.

### 12.4 Long-Vol Advocate

Purpose: present the strongest evidence that realized movement or retained IV will exceed what the selected options price.

System prompt:

```text
You are the Long-Volatility Advocate. You do not predict market direction. Argue only that the magnitude of the move, realized variance, or post-event implied volatility may be greater than the options market has priced.

Use the supplied forecast, IV metrics, execution costs, and evidence items. Every claim must cite evidence IDs or named deterministic metrics. You may support a delta-neutral long straddle or abstention. You may not recommend a call, put, vertical spread, or directional trade.

Address gamma, theta, vega, liquidity, and the forecast interval. State at least one condition that would invalidate your thesis. Do not alter any calculated number. Return only the structured schema.
```

### 12.5 Short-Vol Advocate

Purpose: present the strongest evidence that implied movement is excessive and post-event IV will contract enough to justify a defined-risk short-vol position.

System prompt:

```text
You are the Short-Volatility Advocate. You do not predict market direction. Argue only that realized movement may be smaller than the option-implied move or that post-event implied volatility may contract more than the market price compensates for.

Use the supplied forecast, IV metrics, execution costs, and evidence items. Every claim must cite evidence IDs or named deterministic metrics. You may support a defined-risk delta-neutral iron butterfly or abstention. You may never support naked short options or a directional trade.

Address tail risk, gamma risk, IV crush, liquidity, maximum loss, and the forecast interval. State at least one condition that would invalidate your thesis. Do not alter any calculated number. Return only the structured schema.
```

### 12.6 Model-Risk Critic

Purpose: find reasons the system should not trust the analysis.

System prompt:

```text
You are the independent Model-Risk Critic for an earnings-volatility system. Your priority is preventing unsupported or non-reproducible trades.

Inspect provenance, timestamps, missing data, model confidence, out-of-distribution flags, quantile width, disagreement, liquidity, surface quality, corporate-action risk, and all claims in the long- and short-volatility theses.

You do not select direction or construct a trade. Force NO_TRADE when facts are unsupported, data may contain future information, directional reasoning has leaked into the analysis, or the edge does not clearly survive uncertainty and friction.

Return only the requested structured report. Cite exact evidence IDs, metrics, or checks. Do not invent problems that are not supported by the supplied artifacts.
```

Deterministic checks run before the LLM critic and are merged into the final report. The LLM may add failures but may not remove deterministic failures.

### 12.7 Explainer Agent

The explainer runs only after the final deterministic decision. It converts the receipt into judge-readable prose. It may not change the decision, metrics, strategy, or order.

Required explanation sections:

- What the market priced.
- What the system forecast.
- Why long vol, short vol, or no trade won.
- Main counterargument.
- How gamma, theta, vega, and delta contribute.
- Maximum loss and key rejection conditions.
- Data mode and limitations.

If the explainer fails, the UI renders a deterministic template from the receipt.

### 12.8 Track Compliance Guard

Run schema and textual checks after every LLM output.

Fail when:

- `directional_view` is not `none`.
- The output recommends calls versus puts based on expected direction.
- A thesis uses signed price targets.
- An unsupported evidence ID appears.
- A numeric value conflicts with authoritative state beyond formatting tolerance.
- The output requests bypassing risk controls.

Potentially directional words such as “bullish” and “bearish” should trigger review. They may appear only in quoted source material that is explicitly reframed as uncertainty magnitude and does not affect trade direction.

---

## 13. LangGraph specification

### 13.1 Nodes

Implement these nodes with stable names because the UI and tests reference them:

1. `initialize_run`
2. `validate_event`
3. `fetch_market_snapshot`
4. `filter_option_chain`
5. `event_magnitude_agent`
6. `volatility_quant_agent`
7. `build_features`
8. `forecast_event_move`
9. `forecast_iv_change`
10. `long_vol_advocate`
11. `short_vol_advocate`
12. `model_risk_critic`
13. `track_compliance_guard`
14. `generate_candidates`
15. `reprice_candidates`
16. `select_candidate`
17. `run_risk_gate`
18. `build_decision_receipt`
19. `await_human_approval`
20. `build_order_plan`
21. `submit_paper_order`
22. `reconcile_order`
23. `finalize_run`
24. `reject_run`

### 13.2 Parallel sections

Run in parallel when supported:

- `event_magnitude_agent` and `volatility_quant_agent` after snapshot availability.
- `forecast_event_move` and `forecast_iv_change` after features.
- `long_vol_advocate` and `short_vol_advocate` after forecasts.

### 13.3 Routing

Use explicit conditional routes:

```text
validate_event fail -> reject_run
fetch/filter fail -> reject_run
forecast confidence fail -> build NO_TRADE receipt
critic force_no_trade -> build NO_TRADE receipt
compliance fail -> build NO_TRADE receipt
no candidates -> build NO_TRADE receipt
risk fail -> build NO_TRADE receipt
paper submission disabled -> finalize as preview_only
approval missing/expired -> finalize as awaiting_or_rejected
submission success -> reconcile_order -> finalize_run
submission failure -> finalize_run with execution failure; never fabricate fill
```

### 13.4 Node idempotency

- Read nodes may be retried.
- Model nodes cache by input artifact hash, model version, and prompt version.
- Candidate generation is pure.
- Risk gate is pure.
- Order-plan creation is pure and fingerprinted.
- Order submission checks the fingerprint ledger before sending.
- Reconciliation may be repeated safely.

### 13.5 Checkpointing

Use a local persistent checkpointer suitable for the hackathon, such as SQLite, if compatible with the current LangGraph release. Each run uses `run_id` as thread ID.

Checkpoint after:

- Snapshot normalization.
- Forecasts.
- Agent debate.
- Risk gate.
- Human approval.
- Submission.

Replay mode must be able to resume without making live calls.

### 13.6 Trace events

Each node appends a compact trace event:

```json
{
  "node": "volatility_quant_agent",
  "status": "completed",
  "started_at": "...",
  "completed_at": "...",
  "latency_ms": 184,
  "input_hash": "...",
  "output_hash": "...",
  "summary": "Selected 2026-08-28 expiry; implied move 7.8%",
  "warnings": []
}
```

Do not store chain-of-thought. Show structured conclusions, evidence, tool calls, and calculations only.

---

## 14. Decision receipt

Every completed run, including no-trade and failed runs, must produce an immutable `decision_receipt.json` with:

```json
{
  "schema_version": "1.0",
  "run_id": "uuid",
  "created_at": "UTC timestamp",
  "data_mode": "replay_real",
  "symbol": "NVDA",
  "event": {
    "event_id": "NVDA-2026Q2",
    "event_time": "timestamp",
    "timing": "amc",
    "confirmed": true
  },
  "snapshot_cutoff": "timestamp",
  "market": {
    "spot": 0.0,
    "selected_expiration": "date",
    "atm_strike": 0.0,
    "atm_iv": 0.0,
    "implied_move_pct": 0.0,
    "surface_quality": 0.0,
    "liquidity_score": 0.0
  },
  "forecast": {
    "move_q20": 0.0,
    "move_q50": 0.0,
    "move_q80": 0.0,
    "probability_exceeds_implied": 0.0,
    "iv_change_q50_points": 0.0,
    "calibration_confidence": 0.0,
    "out_of_distribution": false
  },
  "debate": {
    "long_vol": {},
    "short_vol": {},
    "critic": {}
  },
  "decision": "long_straddle",
  "selected_strategy": {},
  "risk_report": {},
  "order_plan": null,
  "execution_receipt": null,
  "rejection_reasons": [],
  "limitations": [],
  "artifact_hashes": {},
  "code_version": "git SHA",
  "model_versions": {},
  "prompt_versions": {}
}
```

Hash the canonical receipt and display its shortened hash in the UI.

---

## 15. Streamlit judge interface

### 15.1 Design goals

The interface must make the quantitative thesis understandable in under 30 seconds. Prefer dense, legible decision information over decorative animation.

Required visual principles:

- Dark neutral background with high contrast.
- One restrained accent for implied volatility, one for long vol, one for short vol, and red only for failure or risk.
- Use the same units everywhere.
- Label every data mode prominently.
- Never hide no-trade or losing replay results.
- Never show chain-of-thought.
- Expandable evidence and trace details are allowed.
- The app must remain usable at 1440×900 and 1920×1080.
- Avoid horizontal scrolling in the main demo path.

Suggested palette:

- Background: `#0B0E14`
- Surface: `#151A23`
- Primary text: `#F4F7FA`
- Secondary text: `#9AA7B8`
- IV accent: `#F2C94C`
- Long vol: `#35C2BD`
- Short vol: `#C084FC`
- Pass: `#3CCB7F`
- Fail: `#FF5C6C`

### 15.2 Navigation

Provide exactly four primary pages or tabs:

1. `Analyze`
2. `Decision`
3. `Replay Scoreboard`
4. `Audit`

Do not add settings, research, portfolio, chat, or admin pages to P0. Put limited demo controls in a sidebar.

### 15.3 Global header

Display:

- CaiSheng logo or wordmark.
- Subtitle: `Earnings Volatility Intelligence Desk`.
- Mode badge: `LIVE`, `REPLAY — REAL`, or `REPLAY — SYNTHETIC`.
- Broker badge: `ALPACA PAPER`, `SIMULATED PAPER`, or `NO EXECUTION`.
- Run ID shortened to eight characters.
- Market clock and timezone.

Synthetic mode must use a persistent warning banner: `Synthetic scenario — excluded from performance metrics.`

### 15.4 Analyze page

Controls:

- Mode selector. Default to `Replay — Real`.
- Scenario selector populated from the replay manifest.
- Live ticker selector restricted to allowlist.
- Risk-budget selector restricted to recommended values and never above hard cap.
- `Run VolAgent Analysis` primary button.
- `Reset Run` secondary button.

Before running, display:

- Event symbol and timestamp.
- Earnings timing and confirmation status.
- Snapshot timestamp or expected live fetch.
- Whether order submission is possible.

During the run, show a compact node timeline:

```text
✓ Snapshot  →  ✓ Event Evidence  →  ✓ Vol Surface
                                  ↓
✓ Forecast  →  ✓ Vol Debate      →  ✓ Model Risk
                                  ↓
✓ Strategies → ✓ Risk Gate       →  Ready
```

For each node show status, one-line result, and latency. Do not stream raw hidden reasoning.

### 15.5 Decision page

The top decision card must include:

```text
NVDA — Earnings Volatility Decision

Market implied move             7.8%
Forecast median move            9.4%
Forecast 20–80 interval         6.1%–13.7%
P(move > implied)               68% calibrated
Forecast post-event IV change   -11.2 points
Edge after friction             +0.9% of spot
Surface quality                 0.91 PASS
Liquidity                       0.87 PASS
Model risk                      PASS

Decision                        LONG STRADDLE
Maximum loss                    $840 / 0.84% NAV
```

The values above are examples only. The implementation must render actual receipt values.

Below the card, show:

1. Forecast distribution overlaid with implied-move threshold.
2. Payoff at expiration and expected exit-value curve as separate labeled traces.
3. Gamma/theta/vega/delta contribution bars.
4. Stress heatmap for underlying move versus IV change.
5. Strategy legs table.
6. Long-vol thesis, short-vol thesis, and critic in three compact columns.
7. Risk-gate checklist.
8. Order preview.

For `NO_TRADE`, replace payoff and order sections with:

- Failed checks.
- Top rejected candidate.
- The minimum change required to reconsider, such as tighter spread or wider model edge.

### 15.6 Order approval interaction

The UI must require:

1. A completed passing risk report.
2. A paper-only badge.
3. A checkbox: `I understand this submits a paper trade only.`
4. A typed confirmation equal to the symbol, such as `NVDA`.
5. A click on `Approve paper order`.

After approval, regenerate and compare the fingerprint. If any quote, quantity, limit price, leg, account, or expiry changed, invalidate approval and require a new preview.

Order submission button states:

- Disabled: no passing candidate.
- Disabled: submission configuration off.
- Disabled: approval incomplete.
- Enabled: valid fresh fingerprint and paper endpoint.
- Loading: one submission in progress; disable duplicate clicks.
- Completed: show receipt.
- Failed: show broker error and reconciliation guidance; never imply a fill.

### 15.7 Replay Scoreboard page

Top metrics:

- Number of eligible events.
- Number of long-vol, short-vol, and no-trade decisions.
- Median move forecast error.
- 20–80 interval coverage.
- Net replay P&L after modeled friction.
- Expected shortfall.
- Maximum drawdown.
- Percentage of P&L attributed to residual delta.

Required charts:

- Forecast versus realized absolute move scatter.
- Calibration or reliability chart.
- Cumulative net P&L with clearly labeled hypothetical replay status.
- Distribution of P&L by strategy.
- Performance by liquidity bucket.
- Full system versus baselines.
- Ablation results.

Required event table:

- Symbol.
- Event date.
- Implied move.
- Forecast median.
- Realized move.
- Decision.
- Net modeled P&L.
- Data quality.
- Receipt link.

Include all eligible consecutive events selected by the manifest rule. Do not default-sort only by largest winners.

### 15.8 Audit page

Display:

- Graph diagram and node status.
- Data provenance table.
- Tool calls and latencies.
- Feature values and missingness.
- Model, prompt, dataset, and code versions.
- All configuration thresholds.
- Full risk checks.
- Receipt JSON with download button.
- Receipt hash.
- Known limitations.
- Tauric Research attribution and other research foundations.

### 15.9 UI failure behavior

- If an LLM is unavailable in replay mode, use precomputed structured outputs and label them `cached replay output`.
- If live data fails, offer replay mode; do not silently switch.
- If a chart cannot render, show the numeric table.
- If account access fails, analysis may continue but order submission remains disabled.
- If no valid option structure exists, show a no-trade decision rather than an empty or crashed page.

---

## 16. Replay dataset and evidence methodology

### 16.1 Purpose

Replay mode serves three purposes:

1. Guarantee a reliable demo outside market hours or without credentials.
2. Provide judge-verifiable evidence across more than one event.
3. Test temporal correctness, agent behavior, and mathematical calculations.

### 16.2 Scenario-selection rule

Define the replay universe before evaluating strategies:

- Start with the configured liquid-symbol allowlist.
- Select consecutive confirmed AMC earnings events during the available historical Alpaca options period.
- Require a complete pre-event underlying snapshot, eligible option expiration, valid entry quotes, post-event exit observations, and provenance.
- Exclude only by documented data-quality rules.
- Do not select events because the strategy won or because the price move was dramatic.

P0 minimum: 20 real scenarios.  
Target: 60 or more real scenarios.  
Strong submission: 100 or more, if obtainable without compromising data quality.

### 16.3 Replay timestamps

For every real scenario store:

- Decision timestamp.
- Event timestamp.
- Entry quote timestamp.
- Exit timestamp.
- Earliest and latest underlying quote timestamps.
- Earliest and latest option quote timestamps.
- Evidence `observed_at` timestamps.

The replay builder must reject any artifact observed after the decision timestamp except explicitly labeled outcome fields used only for scoring.

### 16.4 Replay storage

`manifest.json` must contain:

```json
{
  "schema_version": "1.0",
  "created_at": "...",
  "builder_code_version": "git SHA",
  "selection_rule": "consecutive eligible AMC events for configured symbols",
  "source_descriptions": [],
  "scenario_count_real": 0,
  "scenario_count_synthetic": 0,
  "files": {
    "events.parquet": "sha256",
    "option_quotes.parquet": "sha256",
    "underlying_bars.parquet": "sha256",
    "evidence.jsonl": "sha256"
  },
  "scenarios": [
    {
      "scenario_id": "...",
      "symbol": "...",
      "event_time": "...",
      "data_mode": "replay_real",
      "included": true,
      "exclusion_reason": null
    }
  ]
}
```

Never commit licensed raw data if its license prohibits redistribution. In that case:

- Commit a small permitted demo subset or derived scenario artifact.
- Include a reproducible builder script.
- Document required credentials and license.
- Keep performance claims limited to data that can be audited by judges.

### 16.5 Synthetic scenarios

Synthetic scenarios are allowed only for failure-path demonstrations:

- Stale quotes.
- Crossed market.
- Missing protective wing.
- Event timestamp conflict.
- Extreme IV shock.
- LLM invalid output.
- Duplicate order submission.

Synthetic scenarios must be visibly labeled and excluded from forecast and P&L metrics.

### 16.6 Evidence cards

Instead of building a web-scale research crawler, create a curated `evidence_cards.json` containing research foundations and public methodology lessons.

Each card:

```json
{
  "card_id": "paper-event-risk-001",
  "title": "Pricing Event Risk",
  "authors_or_org": "...",
  "published_at": "...",
  "source_url": "...",
  "source_type": "paper",
  "claim": "...",
  "usable_design_implication": "...",
  "limitations": "...",
  "content_hash": "..."
}
```

Minimum categories:

- Earnings jump and option-pricing research.
- Event risk premia.
- Volatility risk premium.
- Deep hedging or transaction-cost-aware hedging.
- Multi-agent trading frameworks.
- Public quant-firm research process and risk practice.

These cards support the Audit page and README. They do not directly change live trade decisions unless converted into pre-specified, tested features.

### 16.7 Precomputed demo runs

For three featured scenarios, store:

- Normalized snapshot.
- Agent structured outputs.
- Forecast artifacts.
- Candidate strategies.
- Risk report.
- Decision receipt.

The featured set must include:

1. One long-vol decision.
2. One short-vol decision.
3. One no-trade decision.

At least one featured trade should be a historical loser or ambiguous case available from the scenario browser, even if the main five-minute demo uses a clearer example.

---

## 17. Evaluation design

### 17.1 Data partitions

Split chronologically:

- Training: earliest 60% of eligible events.
- Calibration/validation: next 20%.
- Final replay test: latest 20%.

For small datasets, use expanding-window walk-forward evaluation and aggregate only truly out-of-sample predictions. Never random-split earnings events.

Group or audit by event date to prevent same-day cross-sectional leakage. Fit preprocessing only on the training portion.

### 17.2 Baselines

Implement all baselines using the same contract filters, timestamps, and costs:

**B0 — No trade**

- Zero P&L.
- Useful as a risk-free reference, not an alpha comparator.

**B1 — Always long ATM straddle**

- Buy every eligible event.
- Same expiration and fill model.

**B2 — Always short defined-risk iron butterfly**

- Sell every eligible event with the same wing-selection rules.

**B3 — Historical-median rule**

- Long vol when shrunk historical median move exceeds executable implied move plus buffer.
- Short vol when the reverse edge exceeds buffer.
- Otherwise no trade.
- No LLM features.

**B4 — Quant model without agents**

- Full numeric forecast and strategy selector.
- Event magnitude features removed or replaced with missing values.
- No advocate or critic outputs.

**Full VolAgent**

- Numeric forecasts plus validated event features, advocates, critic, compliance guard, and risk gate.

### 17.3 Forecast metrics

Report:

- Median absolute error for absolute move.
- Root mean squared error as secondary.
- Pinball loss for q20, q50, and q80.
- 20–80 interval coverage.
- Average interval width.
- Brier score or log loss for `move > implied` probability.
- Calibration plot.
- IV-change median absolute error and interval coverage.

### 17.4 Strategy metrics

Report after modeled spread, slippage, and fees:

- Total P&L.
- Mean and median P&L per event.
- Hit rate, clearly labeled as insufficient alone.
- Standard deviation.
- Annualized Sharpe only when sampling assumptions are documented.
- Sortino as secondary.
- Maximum drawdown.
- 95% expected shortfall.
- Worst event.
- Turnover and contracts traded.
- Long-vol, short-vol, and no-trade counts.
- Results by year, symbol, liquidity bucket, and forecast-confidence bucket.
- Percentage of P&L attributed to residual delta.

Do not emphasize a Sharpe ratio computed from a tiny or irregular sample without a prominent warning.

### 17.5 Agent metrics

Report:

- Schema-valid output rate.
- Evidence citation validity rate.
- Unsupported claim rate.
- Directional leakage rate.
- Critic abstention rate.
- Average latency and cost per run.
- Decision reproducibility across at least three repeated LLM runs on a small fixed subset.
- Difference between full VolAgent and quant-only baseline.

### 17.6 Ablations

At minimum run:

1. Remove Event Magnitude Agent features.
2. Remove advocate debate.
3. Remove Model-Risk Critic.
4. Replace ML forecast with historical shrinkage baseline.
5. Remove friction buffer to demonstrate why it matters.

If an agent component does not improve forecast, risk, abstention quality, or judge transparency, state that honestly. Agent usefulness may appear as avoided bad trades rather than higher raw P&L.

### 17.7 Statistical honesty

- Report event count with every aggregate.
- Use bootstrap confidence intervals for mean event P&L where feasible.
- Do not claim statistical significance without a valid test and adequate sample.
- Do not tune thresholds on the final test set.
- Freeze the replay manifest before final model comparison.
- Keep an experiment log with configuration and artifact hashes.
- Include losing runs and failed hypotheses.

---

## 18. Execution behavior

### 18.1 Paper-only startup assertion

At startup:

```python
assert settings.alpaca_paper_trade is True
assert settings.execution.paper_only is True
```

Also validate the actual configured base URL or official SDK paper flag. A boolean alone is insufficient if the endpoint can still point to live trading.

### 18.2 Preview

Preview must display:

- Account equity and available buying power.
- Strategy and quantity.
- All leg symbols and actions.
- Limit debit or credit.
- Maximum loss.
- Approval expiry.
- Fingerprint.
- Data and quote age.

Do not claim the broker guarantees the calculated fill or max loss. Max loss is a strategy calculation subject to assignment, exercise, and operational assumptions.

### 18.3 Submission

Before submission, atomically verify:

- Fingerprint is approved and unused.
- Approval is unexpired.
- Quotes are still fresh or the plan explicitly uses the frozen replay simulator.
- Account is paper.
- No identical open order or recently submitted client order ID exists.
- Broker supports the order class and legs.

Then submit exactly once with a unique client order ID.

### 18.4 Reconciliation

After submission:

- Fetch order by ID or client order ID.
- Display parent and leg status.
- Do not infer a fill from submission success.
- Store response hash and normalized receipt.
- On timeout, mark `submission_unknown` and reconcile before allowing another attempt.
- Never resend automatically when state is unknown.

### 18.5 Simulated paper adapter

The simulated adapter must:

- Accept only valid `OrderPlan` objects.
- Use deterministic scenario quotes.
- Return statuses such as accepted, filled, rejected, or expired according to fixture configuration.
- Be labeled `SIMULATED PAPER` everywhere.
- Never be mixed into claims about actual Alpaca execution.

### 18.6 Exercise, assignment, and lifecycle limitation

P0 assumes the strategy is closed at the configured post-event exit time and does not model random early assignment before that exit. Reduce this risk by rejecting ex-dividend windows, adjusted contracts, zero-extrinsic-value short legs, and expirations too close to the event. Display this limitation in the Audit page and replay methodology.

If a real Alpaca paper position remains open:

- Read actual broker position and order state rather than relying on internal expectation.
- Do not automatically exercise, mark do-not-exercise, roll, or close without a separately validated and approved order plan.
- Do not claim that the P0 replay models operational assignment or expiration behavior fully.

---

## 19. Logging, caching, and failure handling

### 19.1 Structured logs

Every log event includes:

- Timestamp UTC.
- Run ID.
- Node name.
- Mode.
- Symbol.
- Event ID if available.
- Severity.
- Event code.
- Human-readable message.
- Artifact hashes when relevant.

Never log secrets, raw authorization headers, full account numbers, or model hidden reasoning.

### 19.2 Cache keys

Use content-derived cache keys:

- Market snapshot: provider + symbol + snapshot cutoff + response hash.
- Agent response: agent version + prompt version + model version + input hash.
- Forecast: model version + feature hash.
- Strategy scenarios: forecast hash + candidate hash + seed.

Live market caches expire quickly. Replay artifacts never mutate.

### 19.3 Error taxonomy

Define explicit errors:

- `ConfigurationError`
- `LiveTradingProhibitedError`
- `DataUnavailableError`
- `StaleQuoteError`
- `TemporalLeakageError`
- `InvalidOptionChainError`
- `InsufficientLiquidityError`
- `ForecastUnavailableError`
- `AgentSchemaError`
- `DirectionalLeakageError`
- `RiskGateRejectedError`
- `ApprovalRequiredError`
- `ApprovalExpiredError`
- `DuplicateOrderError`
- `BrokerSubmissionError`
- `BrokerStateUnknownError`

Convert errors to judge-readable messages at the UI boundary. Preserve technical details in structured logs.

### 19.4 Fail-closed matrix

| Failure | Analysis | Decision | Submission |
|---|---|---|---|
| LLM unavailable in live mode | Partial | No trade | Disabled |
| LLM unavailable in replay with cached output | Allowed, labeled | Allowed | Simulated only |
| Option data unavailable | Stop | No trade | Disabled |
| News unavailable | Continue with warning | Possible with reduced confidence | Possible if all gates pass |
| Account unavailable | Continue | Preview only | Disabled |
| Event time unknown | Stop | No trade | Disabled |
| Quote stale | Stop | No trade | Disabled |
| Critic unavailable | Continue only with deterministic critic fail-safe | No trade by default | Disabled |
| Receipt explanation unavailable | Continue | Deterministic template | Possible if gates pass |
| Submission timeout | Stop | Preserve decision | Reconcile; do not retry automatically |

---

## 20. Testing specification

### 20.1 General standards

- Tests must be deterministic.
- Freeze clocks in time-sensitive tests.
- Use fixed random seeds.
- No live broker order is allowed in CI.
- Network integration tests are opt-in and read-only unless explicitly run in a dedicated paper account.
- Target at least 85% coverage for `quant`, `graph`, `risk`, and `execution` modules.

### 20.2 Unit tests: pricing and IV

Test:

- BSM call and put values against known reference cases.
- Put-call parity within tolerance.
- Greeks against finite differences.
- IV inversion recovers the original volatility from generated prices.
- IV inversion fails cleanly for invalid prices.
- Time-to-expiry and units.
- Vega normalization.

### 20.3 Property tests

Using Hypothesis or equivalent, verify:

- Call price is non-negative and no greater than discounted spot under supported assumptions.
- Put price is non-negative and respects lower/upper bounds.
- Call price generally decreases with strike.
- Put price generally increases with strike.
- Long-straddle maximum loss equals debit.
- Iron-butterfly loss never exceeds computed max loss at expiration over a wide spot range.
- Increasing quantity scales payoff and Greeks linearly.
- Candidate generation never emits an unsupported directional structure.

### 20.4 Unit tests: quote filtering

Test each rejection independently:

- Crossed quote.
- Zero ask.
- Low mid.
- Excessive spread.
- Stale timestamp.
- Low open interest.
- Low volume.
- Adjusted contract.
- Wrong underlying.
- Wrong expiration.

Test audit counts after every stage.

### 20.5 Unit tests: forecasts

- Baseline uses only prior events.
- Shrinkage weights sum to one.
- Quantile order is valid after correction.
- OOD flags trigger on extreme inputs.
- Model artifact includes training cutoff and hashes.
- Probability and confidence are bounded.
- Missing optional features use flags, not silent zero imputation without documentation.

### 20.6 Unit tests: strategy generation

- Correct long-straddle legs and position intents.
- Correct four-leg iron butterfly.
- Symmetric and asymmetric max-loss calculation.
- Wing lookup fails closed when a protective leg is missing.
- Expiration selector follows documented rank.
- Quantity respects risk budget and max contracts.
- Limit price lies between natural and midpoint according to convention.
- Debit, credit, P&L, loss-magnitude, and Greek signs follow section 6.8.

### 20.7 Unit tests: risk gate

Create one test for every hard check. Include:

- Live endpoint rejected even when config says paper.
- Naked short rejected.
- Excess max loss rejected.
- Excess delta rejected.
- Stale quote rejected.
- Directional structure rejected.
- Critic rejection honored.
- Temporal leakage rejected.
- Duplicate fingerprint rejected.
- Expired approval rejected.
- A fully valid candidate passes.

### 20.8 Agent tests

Use recorded or stubbed structured model responses:

- Valid Event Magnitude output passes.
- Missing evidence ID fails.
- Directional language and schema fields fail.
- Altered numeric fact fails.
- Long- and short-vol agents include invalidation conditions.
- Critic cannot remove deterministic failures.
- Invalid JSON retries once and then fails closed.

Do not test semantic correctness solely with another LLM. Prefer deterministic schemas and evidence checks.

### 20.9 Graph tests

Test paths:

1. Successful long-vol preview.
2. Successful short-vol preview.
3. Model selects no trade.
4. Critic forces no trade.
5. Compliance guard forces no trade.
6. Risk gate rejects.
7. LLM timeout in live mode.
8. Cached replay completion.
9. Human approval pause and resume.
10. Paper submission and reconciliation.
11. Unknown broker state blocks duplicate retry.
12. Checkpoint resume does not repeat successful nodes or order submission.

### 20.10 Replay tests

- Manifest hashes validate.
- No future evidence enters feature inputs.
- Synthetic scenarios are excluded from metrics.
- Consecutive-event selection rule is reproducible.
- Baselines and full model use identical cost assumptions.
- Featured receipts reproduce from artifacts.
- Frozen seed yields identical scenario metrics.

### 20.11 UI tests

Using Streamlit’s current supported test utilities where practical:

- App starts without keys in replay mode.
- Mode badge is visible.
- Synthetic warning is visible.
- Analysis button completes a cached run.
- No-trade page renders failure reasons.
- Approval controls remain disabled until requirements pass.
- Double-click cannot submit twice.
- Receipt download is available.
- A numeric-table fallback appears if a chart fixture fails.

### 20.12 Smoke commands

Provide Make targets:

```makefile
make install
make lint
make typecheck
make test
make test-fast
make replay-validate
make replay-score
make demo
make alpaca-readonly-smoke
```

`make demo` must launch a working replay experience without secrets.

---

## 21. Implementation milestones and stop conditions

### Milestone 0 — Skeleton and safety

Deliver:

- Package layout.
- Configuration.
- Structured logging.
- Domain schemas.
- Paper-only startup assertion.
- Replay fixture loader.

Exit criteria:

- App starts in replay mode without keys.
- A live endpoint configuration is rejected.
- Formatting, lint, type checks, and schema tests pass.

### Milestone 1 — Deterministic quant vertical slice

Deliver:

- Quote filtering.
- Expiration and ATM selection.
- Implied move.
- BSM/IV/Greeks checks.
- Baseline movement forecast.
- Long straddle and iron butterfly generation.
- Payoff, scenario repricing, selector, and risk gate.
- CLI decision receipt from one replay fixture.

Exit criteria:

- One long-vol, one short-vol, and one no-trade fixture produce correct receipts.
- All property and risk tests pass.

Do not begin fancy UI or extra agents before this milestone passes.

### Milestone 2 — Agent graph

Deliver:

- Event Magnitude Agent.
- Long-Vol and Short-Vol Advocates.
- Model-Risk Critic.
- Compliance guard.
- LangGraph routing and checkpoints.
- Cached outputs for featured scenarios.

Exit criteria:

- All graph paths pass.
- No directional structure can reach candidate selection.
- Provider failure yields no trade or cached replay behavior.

### Milestone 3 — Judge UI

Deliver:

- Four pages.
- Node timeline.
- Decision card.
- Forecast, payoff, attribution, and stress charts.
- Debate and risk cards.
- Receipt download.

Exit criteria:

- A first-time tester can complete the replay demo in under five minutes.
- App works at the target viewport.
- No keys or network are required.

### Milestone 4 — Alpaca integration

Deliver:

- Read-only SDK adapter.
- Option chain normalization.
- Paper account adapter.
- Multi-leg preview and submission.
- Reconciliation.
- MCP adapter or demonstrable official MCP integration.

Exit criteria:

- Read-only smoke succeeds when credentials are present.
- A dedicated paper-account test submits at most one explicitly approved test order.
- Duplicate protection works.
- Replay remains functional when Alpaca is unavailable.

### Milestone 5 — Replay evidence

Deliver:

- Frozen manifest.
- Real scenarios.
- Trained baseline and optional quantile models.
- Baselines, ablations, metrics, and scoreboard.

Exit criteria:

- Every reported metric is reproducible.
- Synthetic events are excluded.
- No temporal leakage is detected.
- Winning and losing events are visible.

### Milestone 6 — Submission hardening

Deliver:

- README.
- Architecture diagram.
- Demo video or script.
- Attribution and licenses.
- Clean setup.
- Full test run.
- Backup demo package.

Exit criteria:

- Fresh clone to working replay demo follows one documented command sequence.
- Five consecutive full demo rehearsals succeed.
- A network-off rehearsal succeeds in replay mode.
- A market-closed rehearsal succeeds.

### Stop conditions

Cut stretch work immediately if any of these remain broken:

- Replay startup without keys.
- Quant calculations or risk tests.
- Track-compliance tests.
- Main five-minute path.
- Alpaca paper/live separation.
- Receipt reproducibility.

---

## 22. README and submission package

### 22.1 README order

The README must contain, in this order:

1. Title and one-line pitch.
2. 30-second GIF or screenshot.
3. Track fit: movement and IV, not direction.
4. What is novel.
5. Architecture diagram.
6. Five-minute quick start in replay mode.
7. Optional Alpaca setup.
8. Mathematical methodology.
9. Agent roles and deterministic authority.
10. Replay evaluation and limitations.
11. Safety: paper-only.
12. Project structure.
13. Test commands.
14. Tauric Research inspiration and attribution.
15. Research references.
16. Disclaimer.

### 22.2 Quick start

Target experience:

```bash
git clone <submission-url>
cd volagent-alpha
uv sync
uv run streamlit run app.py
```

The app should open in replay mode with a featured scenario ready.

### 22.3 Submission assets

Include:

- One architecture diagram.
- One screenshot of the decision card.
- One screenshot of the replay scoreboard.
- A 60–120 second backup video showing the complete path.
- A sample decision receipt.
- A sample no-trade receipt.
- Test summary.
- License and NOTICE.

### 22.4 Claims policy

Allowed:

- “Paper-trading prototype.”
- “Historical replay under documented assumptions.”
- “Inspired by TradingAgents.”
- “Forecasts unsigned event movement and IV change.”

Forbidden unless independently proven:

- “Production-grade.”
- “Institutional-grade alpha.”
- “Guaranteed profit.”
- “Autonomous hedge fund.”
- “Backtest proves future performance.”
- “Probability of profit” without the word “model.”
- “Live Alpaca fill” when using simulated replay.

---

## 23. Judge questions and required answers

### Why use agents instead of one model?

The roles consume different evidence and have different failure objectives. Event Magnitude extracts uncertainty from text, Volatility Quant analyzes the option surface, opposing advocates stress-test the forecast, and Model Risk can force abstention. The final trade and risk calculations remain deterministic. The replay ablation shows whether agents add value beyond the quant-only baseline.

### Where does the potential edge come from?

The edge is not “AI sentiment.” It is the difference between the physical distribution of event movement and IV change forecast from point-in-time evidence and the distribution priced by executable option quotes, after friction and uncertainty.

### Are you predicting direction?

No. The target is absolute log return and event variance. Monte Carlo signs are symmetric. Structures are approximately delta-neutral and directional structures are rejected by schema and risk controls.

### How do you prevent hallucinations?

LLMs cannot create prices, forecasts, strategies, risk results, or orders. They cite supplied evidence IDs and return typed schemas. Deterministic guards reject unsupported evidence, conflicting numbers, directional leakage, and risk violations.

### Why LangGraph?

It makes parallel specialist work, conditional abstention, checkpoints, human approval, and the traceable state transition visible and testable.

### Why Alpaca?

Alpaca provides current options chains and Greeks, market/news/account data, multi-leg paper execution, and an official MCP server. The integration covers the full path from evidence to paper-order receipt.

### How is this different from TradingAgents?

TradingAgents provides the organizational inspiration. CaiSheng replaces directional stock analysis with event-variance and IV forecasting, adds a deterministic option repricer and risk optimizer, and learns from calibrated event errors and Greek-attributed P&L.

### Is the backtest realistic?

It is a historical replay, not a guarantee. It uses point-in-time inputs, chronological validation, conservative bid/ask fills, fees, slippage, defined selection rules, and sealed manifests. Limitations are shown alongside results.

### What happens when the agents disagree?

Disagreement widens the uncertainty penalty. If the numerical edge does not survive it, the system abstains. An LLM vote cannot force a trade.

### What is the most important risk control?

There is no single control: the system requires defined risk, fresh liquid quotes, confirmed event timing, a calibrated edge after costs, delta limits, stress limits, critic approval, and a one-time human-approved paper-order fingerprint.

---

## 24. Final acceptance criteria

### 24.1 Track compliance

- [ ] The predictive target is unsigned event movement and IV change.
- [ ] No directional strategy exists in candidate-generation code.
- [ ] Agent schemas require `directional_view="none"`.
- [ ] A compliance test rejects directional leakage.
- [ ] Every trade receipt contains an explicit IV or event-variance thesis.
- [ ] P&L attribution reports delta separately and shows low expected directional exposure.

### 24.2 Mathematical rigor

- [ ] Quote filters and units are tested.
- [ ] Implied move uses documented executable and midpoint measures.
- [ ] Pricing, IV inversion, and Greeks pass reference and property tests.
- [ ] Forecasts are chronological and calibrated.
- [ ] Monte Carlo is seeded and reproducible.
- [ ] Expected value includes spread, slippage, and fees.
- [ ] Expected shortfall and stress losses are reported.
- [ ] `model probability` is labeled correctly.
- [ ] No midpoint-only performance claim exists.

### 24.3 Agent integrity

- [ ] Every factual LLM claim cites a valid evidence ID or authoritative metric.
- [ ] Invalid output retries once and then fails closed.
- [ ] Critic can force no trade.
- [ ] Deterministic failures cannot be removed by an LLM.
- [ ] Chain-of-thought is not stored or displayed.
- [ ] Cached replay output is labeled.

### 24.4 Safety and execution

- [ ] Application cannot start against a live-money endpoint.
- [ ] Order submission is off by default.
- [ ] Only Alpaca paper or simulated paper adapters exist in the demo build.
- [ ] Every short structure has protective wings.
- [ ] All passing trades respect the hard NAV risk cap.
- [ ] Human approval is fingerprinted, expiring, and one-time.
- [ ] Submission timeouts reconcile before retry.
- [ ] Duplicate-click test passes.

### 24.5 Replay evidence

- [ ] At least 20 real historical scenarios are included or reproducibly buildable.
- [ ] Selection rules are frozen before final scoring.
- [ ] Manifest hashes validate.
- [ ] No future information enters features.
- [ ] Synthetic events are excluded from metrics.
- [ ] Baselines use identical costs.
- [ ] Losing and no-trade events are visible.
- [ ] Metrics report sample sizes and limitations.

### 24.6 Judge experience

- [ ] Fresh replay startup requires no credentials.
- [ ] Main path completes in under five minutes.
- [ ] The decision card is understandable without reading transcripts.
- [ ] Node trace shows real specialized work.
- [ ] Payoff, forecast, Greeks, and stress charts render.
- [ ] Alpaca integration is visible and accurately labeled.
- [ ] Failure scenario ends in a clear no-trade decision.
- [ ] Five consecutive rehearsals pass.
- [ ] Network-off replay rehearsal passes.

### 24.7 Documentation and attribution

- [ ] README follows the required order.
- [ ] Setup commands work from a fresh clone.
- [ ] TradingAgents inspiration is cited.
- [ ] Apache-2.0 requirements are followed if code is reused.
- [ ] Research sources are linked.
- [ ] Limitations and paper-only disclaimer are prominent.

---

## 25. Definition of done

The hackathon build is done when a judge can open the app without credentials, select a real sealed earnings scenario, watch specialized LangGraph nodes produce evidence-constrained long- and short-volatility theses, inspect a calibrated movement-versus-implied-volatility decision, see deterministic strategy and risk calculations, review a reproducible scoreboard, and optionally submit the exact approved multi-leg order to an Alpaca paper account—without any directional prediction, live-money capability, hidden future data, fabricated result, or manual repair during the demonstration.

Do not continue adding features after this definition is satisfied until the submission package, tests, and rehearsals are complete.

---

## 26. Authoritative external references

Use current official documentation during implementation. These links establish the intended sources but their exact APIs must be rechecked at build time.

### Architecture and agent inspiration

- TradingAgents repository: <https://github.com/TauricResearch/TradingAgents>
- TradingAgents paper: <https://arxiv.org/abs/2412.20138>
- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph/overview>
- LangGraph persistence: <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph interrupts: <https://docs.langchain.com/oss/python/langgraph/interrupts>

### Alpaca

- Alpaca MCP server: <https://docs.alpaca.markets/us/docs/alpaca-mcp-server>
- Alpaca options trading overview: <https://docs.alpaca.markets/us/docs/options-trading-overview>
- Alpaca multi-leg options: <https://docs.alpaca.markets/us/docs/options-level-3-trading>
- Alpaca historical option data: <https://docs.alpaca.markets/us/docs/historical-option-data>
- Alpaca real-time option data: <https://docs.alpaca.markets/us/docs/real-time-option-data>
- Alpaca option-chain endpoint: <https://docs.alpaca.markets/us/v1.4.2/reference/optionchain>

### Research and public data

- Semantic Scholar API: <https://www.semanticscholar.org/product/api/>
- SEC EDGAR APIs: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- FRED and ALFRED API: <https://fred.stlouisfed.org/docs/api/fred/series/alfred.html>
- OPHR multi-agent volatility trading paper: <https://papers.neurips.cc/paper_files/paper/2025/file/4c7dbef8023a15c4b81dc95a6ea08bf3-Paper-Conference.pdf>
- Ex-Ante Risk Premia on Earnings Announcements: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4342267>
- Pricing Event Risk: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3840081>
- Accounting for Earnings Announcements in Option Pricing: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2462298>
- AQR, Understanding the Volatility Risk Premium: <https://www.aqr.com/Insights/Research/White-Papers/Understanding-the-Volatility-Risk-Premium>
- AQR, Being Right Is Not Enough: <https://www.aqr.com/Insights/Research/Working-Paper/Being-Right-is-Not-Enough-Buying-Options-to-Bet-on-Higher-Realized-Volatility>
- Deep Hedging with transaction costs: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3514586>

### Public quant-process references

- Two Sigma approach: <https://www.twosigma.com/about-us/>
- Man AHL approach: <https://www.man.com/ahl>
- CFM research and implementation approach: <https://www.cfm.com/cfm-our-approach/>

---

## 27. Compact master prompt for a coding agent

Copy this prompt together with the complete specification when assigning implementation:

```text
Build CaiSheng exactly according to VolAgent-Alpha-Hackathon-Build-Spec.md.

Priorities are: paper-only safety, strict Options Alpha non-directional compliance, a deterministic quantitative vertical slice, a reliable five-minute replay demo, historical evaluation, Alpaca integration, then visual polish.

Do not expand scope. Implement milestones in order. Do not begin extra agents, calendar spreads, macro events, research crawling, autonomous scheduling, or production infrastructure before every P0 acceptance criterion passes.

The system predicts absolute earnings movement and post-event IV change, never price direction. LLMs may interpret and challenge supplied evidence but cannot create prices, forecasts, strategies, risk approvals, or broker payloads. Candidate strategies are limited to a delta-neutral long straddle, a defined-risk short iron butterfly, or no trade. The deterministic risk gate is final.

Start by inspecting the repository and current official APIs. Produce an implementation plan mapped to the specification milestones. After each milestone, run and report the required tests. Never describe synthetic, replay, preview, submitted, or filled states inaccurately. Never enable live-money trading.
```

---

## 28. Ordered implementation backlog

The implementation agent should convert these items into its task tracker. `Depends on` means the task must not be considered complete before its dependency passes.

| ID | Priority | Task | Depends on | Completion evidence |
|---|---:|---|---|---|
| VA-001 | P0 | Inspect repository, `AGENTS.md`, official rules, and current APIs | — | Written findings and changed-assumption list |
| VA-002 | P0 | Create Python package, lockfile, Make targets, lint/type/test config | VA-001 | Clean install and empty test suite pass |
| VA-003 | P0 | Implement settings, YAML loading, UTC clock, and paper-only assertions | VA-002 | Live endpoint rejection test |
| VA-004 | P0 | Implement enums, provenance, market, event, forecast, strategy, risk, execution, and state schemas | VA-002 | Schema tests and JSON examples |
| VA-005 | P0 | Implement structured logging, hashing, canonical JSON, and run IDs | VA-003, VA-004 | Secret-redaction and stable-hash tests |
| VA-006 | P0 | Implement replay manifest and fixture loader | VA-004, VA-005 | One verified real or permitted demo fixture loads |
| VA-007 | P0 | Implement quote normalization and filtering audit | VA-004 | Unit tests for every rejection reason |
| VA-008 | P0 | Implement market conventions, expiry selection, forward/ATM selection | VA-007 | Deterministic selection fixture |
| VA-009 | P0 | Implement BSM pricing, bounds, Greeks, and IV inversion | VA-004 | Reference and property tests |
| VA-010 | P0 | Implement implied move, surface diagnostics, realized-vol features | VA-007–VA-009 | Golden feature fixture |
| VA-011 | P0 | Implement historical shrinkage baseline and uncertainty | VA-010 | No-future-data and shrinkage tests |
| VA-012 | P0 | Implement IV-change baseline and scenario distribution | VA-010, VA-011 | Fixed-seed forecast artifact |
| VA-013 | P0 | Implement straddle and iron-butterfly factories | VA-007–VA-010 | Exact-leg and max-loss tests |
| VA-014 | P0 | Implement conservative fill model, Monte Carlo repricer, and P&L attribution | VA-012, VA-013 | Reproducible scenario result |
| VA-015 | P0 | Implement risk-adjusted selector and all hard risk checks | VA-014 | One passing and every failing risk test |
| VA-016 | P0 | Emit deterministic decision receipt through CLI | VA-005, VA-015 | Long, short, and no-trade golden receipts |
| VA-017 | P0 | Implement LLM client boundary, prompt versions, schema validation, and cache | VA-004, VA-005 | Stubbed valid/invalid response tests |
| VA-018 | P0 | Implement Event Magnitude, Long-Vol, Short-Vol, Model-Risk, Explainer, and Compliance agents | VA-017 | Evidence and directional-leakage tests |
| VA-019 | P0 | Assemble LangGraph nodes, parallel edges, routes, and checkpointing | VA-016, VA-018 | All graph-path tests |
| VA-020 | P0 | Build Analyze and Decision Streamlit pages | VA-019 | Featured scenarios render end to end |
| VA-021 | P0 | Build charts, stress heatmap, risk checklist, and receipt download | VA-014, VA-020 | Screenshot and UI smoke tests |
| VA-022 | P0 | Build replay evaluation, B0–B4 baselines, and Scoreboard page | VA-006, VA-011–VA-016 | Reproducible score report |
| VA-023 | P0 | Build Audit page with provenance, versions, thresholds, traces, and attribution | VA-019–VA-022 | Complete audit for one run |
| VA-024 | P0 | Implement Alpaca SDK read-only market/account adapters | VA-004, VA-007 | Optional credentialed read-only smoke |
| VA-025 | P0 | Implement paper multi-leg order planning, approval fingerprint, submission, and reconciliation | VA-003, VA-015, VA-024 | Dedicated paper-account integration test |
| VA-026 | P0 | Implement official Alpaca MCP adapter or documented MCP path | VA-024 | Tool discovery and normalized option-chain result |
| VA-027 | P0 | Build at least 20 eligible real replay scenarios and synthetic failure fixtures | VA-006, VA-024 | Frozen manifest and validation report |
| VA-028 | P0 | Precompute three featured runs and validate offline demo | VA-019, VA-027 | Long, short, no-trade cached receipts |
| VA-029 | P0 | Complete README, NOTICE, methodology, limitations, and demo script | VA-022–VA-028 | Fresh-reader documentation review |
| VA-030 | P0 | Run full quality suite and five demo rehearsals | All P0 | Test report and rehearsal log |
| VA-031 | P1 | Train chronological quantile and probability models if data minimum is met | VA-027 | Model card and walk-forward report |
| VA-032 | P1 | Add bootstrap intervals and repeated-agent ablations | VA-022, VA-031 | Updated scoreboard |
| VA-033 | P1 | Add Dockerized replay demo | VA-020–VA-023 | One-command container run |
| VA-034 | P1 | Record backup demo video and capture final screenshots | VA-030 | Submission assets |
| VA-035 | P2 | Add delta-neutral double-calendar strategy | All P0 | Separate tested feature flag |
| VA-036 | P2 | Add one scheduled macro-event workflow | All P0 | Separate replay methodology |

The implementation agent must not start P1 while any P0 safety, mathematical, track-compliance, replay, or main-demo-path task is incomplete.
