# CaiSheng Alignment With Alpaca's Multi-Agent Trading Architecture

**Research date:** 2026-09-02  
**Scope:** Alpaca's article, current official Alpaca documentation and official `alpacahq` repositories, plus a focused read-only inspection of CaiSheng.  
**Post-remediation verdict:** CaiSheng is strongly aligned with the article's substantive architecture and is materially safer for multi-leg options. It now proves agent runtime mode and Alpaca feed identity in each decision record. The remaining architectural improvements—TradingStream and a decision-bound official-MCP cross-check—are useful but non-blocking for this low-frequency hackathon submission. Overall: **strong, truthful Alpaca integration with broker P&L evidence still to be accumulated**.

## Important source distinction

The requested article, [Building a Multi-Agent AI Trading System on Alpaca](https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca), is hosted by Alpaca but is explicitly an individual user's educational prototype. Its disclaimer says the views are the author's, the strategies and results are illustrative, and Alpaca does not endorse them. It is therefore a useful architecture case study, **not an Alpaca specification or required blueprint**.

Alpaca's official API documentation and official `alpacahq` repositories are authoritative for API behavior, paper-trading assumptions, market-data entitlements, MCP configuration, and SDK capabilities:

- [Alpaca paper-trading documentation](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca Market Data API documentation](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Alpaca options-trading documentation](https://docs.alpaca.markets/us/docs/options-trading)
- [Alpaca-py `TradingStream`](https://alpaca.markets/sdks/python/api_reference/trading/stream.html)
- [Alpaca-py option live-data stream](https://alpaca.markets/sdks/python/api_reference/data/option/live.html)
- [Official Alpaca MCP Server V2](https://github.com/alpacahq/alpaca-mcp-server)
- [Official Alpaca agent skills](https://github.com/alpacahq/alpaca-skills)

## What the article actually builds

The article's concrete pipeline is:

```text
Alpaca OHLCV + supplemental sources
    -> regime-aware screener
    -> five isolated research agents in parallel
    -> independent critic
    -> human approve/reject/revise gate
    -> deterministic Python risk guard
    -> Alpaca execution
    -> recurring position monitor
```

Its important design properties are:

1. **One normalized snapshot:** Data from Alpaca and supplemental sources is consolidated before agents run. Agents do not independently fetch mutable data.
2. **Specialized, isolated roles:** Each research agent evaluates a different lens and cannot see other proposals before submitting its own structured result.
3. **Fixed proposal contracts:** Every proposal has required fields for thesis, entry, exits, macro alignment, and confidence.
4. **Independent criticism:** The proposer does not validate its own work. The critic checks a governance memo and structural validity rather than predicting returns.
5. **Human accountability:** The paper-stage prototype requires approve/reject/revise before execution.
6. **Deterministic risk:** Position, sector, leverage, and drawdown limits are Python rules with unit tests; no model may override them.
7. **Broker-backed lifecycle:** Alpaca handles market data, paper order submission, positions, and monitoring.
8. **Decision evidence:** Proposals, critic warnings, approval decisions, and exits remain traceable.

The article reports a very small, changing-parameter simulation. Its P&L and agent rankings are explicitly hypothetical and limited; they are not evidence that five-agent debate creates alpha.

## Essential principles versus illustrative choices

| Article element | Keep as a principle? | Applicability to CaiSheng |
|---|---:|---|
| One point-in-time normalized snapshot | Yes | Essential for preventing temporal disagreement and leakage. |
| Specialized parallel proposals | Yes | Useful when roles have genuinely different inputs/objectives. Agent count itself has no value. |
| Typed, structured outputs | Yes | Essential for deterministic validation and auditability. |
| Independent critic | Yes | Essential, but the critic must not be treated as an alpha model. |
| Deterministic, non-bypassable risk guard | Yes | Essential. CaiSheng is stronger here than the article. |
| Persistent decision and execution records | Yes | Essential for judging, recovery, and P&L attribution. |
| Exact number of five agents | No | Illustrative. CaiSheng's volatility-specific roles are more coherent for its strategy. |
| S&P 500 universe and 2–28 day holding period | No | Strategy-specific, not an Alpaca requirement. |
| Finnhub, yfinance, and FRED | No | Useful only if the strategy needs those features and their point-in-time provenance can be guaranteed. |
| SQLite | No | The invariant is durable, transactional state; the storage engine is an implementation choice. |
| Per-trade human approval | Depends | Appropriate during early paper validation. CaiSheng's time-limited operator lease is a defensible human accountability boundary for controlled autonomy. |
| Market entry plus equity OCO bracket | No | The article's example is not a blueprint for CaiSheng's atomic multi-leg option orders. |
| Fifteen-minute polling | No | A prototype interval, not an optimal Alpaca integration pattern. |
| The article's position/sector/drawdown percentages | No | Illustrative limits that must be derived from CaiSheng's own mandate. |

## Focused CaiSheng alignment audit

### Strongly aligned and verified in code

| Principle | CaiSheng evidence | Assessment |
|---|---|---|
| Real Alpaca market data | `src/volagent/data/alpaca_sdk.py` uses `StockHistoricalDataClient`, `OptionHistoricalDataClient`, `TradingClient`, stock quotes, option-chain snapshots, contracts, Greeks, IV, open interest, and bounded volume batches. | **Strong** |
| Shared snapshot before debate | `fetch_market_snapshot` populates underlying, event, option chain, evidence, timestamps, and hashes before the parallel LangGraph branches. | **Strong** |
| Parallel specialization | `src/volagent/graph/builder.py` uses LangGraph fan-out/fan-in for event magnitude versus volatility quant, then long-vol versus short-vol advocates. | **Strong** |
| Structured messages | Pydantic models in `src/volagent/domain/state.py` reject extra fields and constrain scores, direction, citations, and critic recommendations. | **Strong** |
| Independent critic | `src/volagent/agents/model_risk.py` checks missing advocates, quote age, temporal leakage, liquidity, OOD state, directional leakage, and disagreement; it can force `NO_TRADE`. | **Strong** |
| Deterministic economic selection | Forecasting, Monte Carlo repricing, strategy selection, portfolio allocation, and risk checks run in deterministic code rather than an LLM. | **Stronger than article** |
| Deterministic hard risk | `src/volagent/quant/risk_gate.py`, `portfolio_gate.py`, and `config/competition.yaml` enforce defined risk, quantity, delta, stress loss, reserved risk, daily entry, daily-loss, and drawdown limits. | **Stronger than article** |
| Alpaca options execution | `src/volagent/execution/alpaca.py` creates Alpaca Level-3 `mleg` limit requests with exact OCC contracts and `position_intent`, and routes them through one approval/idempotency boundary. | **Strong and options-native** |
| Durable lifecycle state | `src/volagent/execution/ledger.py` persists decisions, intents, receipts, reconciliation, positions, benchmark intents, halts, and audit events. | **Strong** |
| Monitoring and recovery | `LifecycleRunner`, `OrderWatcher`, `PositionMonitor`, and two-way broker reconciliation repeatedly compare exact contracts and can send risk-reducing close orders. | **Strong** |
| Human accountability | Competition entries require a time-limited, account-bound operator lease; stop revokes new entries while monitoring continues. | **Strong, different from article** |
| Official Alpaca technologies | `src/volagent/integrations/alpaca_lockbox.py` checks the official CLI, official MCP V2, and official Alpaca skills. Official MCP is intentionally restricted to read-only toolsets. | **Good sponsor integration** |
| Auditable output | `caisheng.decision.v1` hashes snapshot metadata, volatility view, all proposals, selected action, risk checks, and critic verdict. | **Strong** |

### Remediated findings and remaining limitations

#### REMEDIATED — Every decision proves whether an AI model participated

`caisheng.decision.v1` now records each role as `deterministic`, `llm_assisted`, `deterministic_fallback`, or `disabled`, together with model identifier, latency, schema-validation status, and sanitized error type when applicable. The competition path is truthful when it uses deterministic synthesis; it does not pretend an LLM ran. Pricing, forecasts, expected value, contract selection, sizing, risk, execution, monitoring, and reconciliation remain deterministic authorities.

#### REMEDIATED — Feed entitlement is carried into decision evidence

Official Alpaca documentation currently states that the Basic Trading API plan receives IEX equities data and an **indicative options feed**, whereas the paid plan provides broader equities coverage and OPRA options data. Paper fills are simulated against current market prices and do not reproduce market impact, queue position, latency slippage, regulatory fees, or NBBO quantity constraints. See [Market Data API plans](https://docs.alpaca.markets/us/docs/about-market-data-api) and [paper-trading limitations](https://docs.alpaca.markets/us/docs/paper-trading).

CaiSheng now explicitly requests and persists the equities and options feed identifiers in snapshots and decision records. Competition mode declares IEX equities and indicative options data, and the judge UI carries the indicative-feed caveat. Broker receipts retain fills for comparison with the locked decision quote. Paper fills remain labelled as simulated broker evidence rather than proof of live execution quality.

#### P1 — Order state is polled; Alpaca's trade-update stream is unused

The current watcher polls `get_orders`, and the monitor polls positions and fresh chains. Polling and reconciliation must remain as recovery mechanisms, but Alpaca-py provides `TradingStream.subscribe_trade_updates` for real-time account order updates. Official Alpaca guidance also recommends WebSocket order updates. See [`TradingStream`](https://alpaca.markets/sdks/python/api_reference/trading/stream.html) and [working with orders](https://docs.alpaca.markets/us/docs/working-with-orders).

Recommended architecture:

```text
TradingStream event
    -> validate broker order/client_order_id
    -> idempotently update ledger
    -> wake watcher/monitor if needed

periodic REST reconciliation
    -> remains authoritative recovery for disconnects, missed events, and restarts
```

An `OptionDataStream` can reduce quote latency for already-open exact contracts, but it should be an optimization after the order-update stream. REST snapshots remain appropriate for atomic pre-trade chain selection. Alpaca supports HTTP and WebSocket market data, including a dedicated option stream: [OptionDataStream](https://alpaca.markets/sdks/python/api_reference/data/option/live.html).

#### P1 — Official MCP is proven, not operationally meaningful inside the decision path

CaiSheng's Lockbox correctly restricts official MCP V2 to `assets,options-data` and rejects mutating tool names. This follows the official server's `ALPACA_TOOLSETS` model; the official MCP repository says tool filtering is server-side and distinguishes `trading`, `assets`, `stock-data`, and `options-data` toolsets. See [official MCP V2 configuration](https://github.com/alpacahq/alpaca-mcp-server#configuration).

This is a good safety boundary. However, the current official MCP use is a technology proof, while live decisions use alpaca-py. Do **not** add an MCP trading path merely for points; it would create a second execution authority. The meaningful optimization is one read-only, audited, judge-visible cross-check—for example, official MCP clock plus exact option-chain discovery compared with the SDK snapshot—while keeping all orders behind CaiSheng's canonical gateway.

#### P1 — Live earnings research inputs are incomplete

The article layers earnings calendars, fundamentals, insider data, cross-asset data, and FRED onto Alpaca OHLCV. CaiSheng correctly notes that Alpaca price data is not an authoritative earnings calendar, but its cloud loop has no verified upstream earnings-calendar/evidence client. Its competition fallback therefore relies on daily ETF volatility opportunities, and the event agent often has no textual evidence.

This gap matters only if the submission claims live earnings intelligence. For a seven-day competition, it is rational to keep the liquid-ETF path primary. If earnings are shown, add one point-in-time calendar/evidence adapter with source URL, observed time, and content hash; do not add four data vendors merely to resemble the article.

#### P2 — Rate-limit and dependency health telemetry is incomplete

The article's useful operational lesson is bulk retrieval and active rate-limit monitoring. CaiSheng batches recent option-volume requests in groups of 100, and its live universe is small, so duplicating a 500-symbol bulk pull is unnecessary. What is still valuable is explicit telemetry for HTTP 429s, retry/backoff, source latency, last successful snapshot, and source-specific circuit breaking.

#### P2 — Feedback claims must remain economic, not agent-themed

The article says outcomes feed back into agent logic but gives no rigorous online-learning protocol. CaiSheng should not auto-edit prompts or weights from a few paper trades. Its benchmark/shadow-book design is better: lock forecasts and counterfactuals before outcomes, then compare selected and rejected policies after the exit. Any parameter change should be versioned and evaluated walk-forward before deployment.

## Recommended optimization order

1. **Expose agent-runtime truth in every decision and on the judge dashboard.** This closes the largest credibility gap without weakening quant safety.
2. **Persist Alpaca feed identity and paper-execution limitations.** Show locked quote, actual fill, slippage, and feed entitlement together.
3. **Add Alpaca `TradingStream` as a low-latency event source, with REST reconciliation retained as the recovery oracle.**
4. **Make one official MCP read-only cross-check operational and visible.** Keep MCP trading disabled so the canonical execution gateway remains unique.
5. **Add rate-limit/source-health receipts.** Surface `429`, latency, retries, and stale-source circuit breakers.
6. **Only then add a verified earnings evidence source** if earnings opportunities are required during the remaining competition window.

Do not spend hackathon time adding more research agents, an S&P 500-wide screener, FRED, or a new database merely to copy the article. None of those changes directly improves CaiSheng's present decision quality, broker safety, or judge evidence.

## Concise implementation acceptance checklist

### Alpaca market data

- [x] Uses official alpaca-py clients for stock and option data.
- [x] Validates timestamps, crossed/non-finite quotes, spread, volume, open interest, IV, and Greeks.
- [x] Uses one locked snapshot for all parallel branches.
- [x] Persists explicitly requested stock/options feed identity in the snapshot and decision record.
- [x] Preserves the locked decision quote and Alpaca fill fields needed to show realized slippage once a lifecycle closes.
- [ ] Emits source latency, retries, HTTP 429, and circuit-breaker status.

### Multi-agent integrity

- [x] LangGraph has real parallel fan-out/fan-in.
- [x] Roles have distinct responsibilities and typed outputs.
- [x] Independent critic can force `NO_TRADE`.
- [x] LLM outputs cannot override deterministic pricing, risk, or execution.
- [x] Every decision proves whether LLM inference ran or deterministic fallback was used.
- [x] Any LLM-assisted mode records model identity, latency, schema validation, and fallback status.

### Trading and lifecycle

- [x] Paper-only endpoint is enforced.
- [x] Atomic multi-leg limit orders use exact contracts and position intents.
- [x] Submission is idempotent and reconciled by client order ID.
- [x] Positions and exact-contract exits are continuously monitored.
- [x] Operator lease provides time-limited human authorization and an emergency halt.
- [ ] Alpaca `TradingStream` updates the ledger in real time.
- [ ] Periodic REST reconciliation proves recovery after stream disconnect or restart.

### Alpaca MCP, CLI, and skills

- [x] Official CLI is verified against the paper endpoint.
- [x] Official MCP V2 is dynamically discovered with read-only toolsets.
- [x] Official Alpaca skills are installed/verified.
- [x] Mutating MCP tools are excluded from the official proof process.
- [ ] One official MCP read-only result is bound to a live decision/preflight receipt, not shown only as a standalone technology demonstration.

### Judge evidence

- [x] Every scan emits a hashed `caisheng.decision.v1` record.
- [x] Risk, critic, proposal, broker, and reconciliation evidence is durable.
- [x] Synthetic replay is labelled separately from broker performance.
- [x] The dashboard states agent runtime mode and Alpaca data feed next to each trade.
- [x] The implemented closed-trade receipt links locked thesis, max risk, Alpaca entry/exit IDs, fills, net P&L, and benchmark counterfactuals; the fresh competition account has not yet produced such a lifecycle.

## Bottom line

CaiSheng already applies the article's most valuable principle—**models may propose and explain, but deterministic code governs money**—more rigorously than the illustrative system. It should not copy the article's five-agent count, equity order example, polling interval, or data-vendor stack.

The most defensible description today is:

> CaiSheng is an Alpaca-native, LangGraph-orchestrated options decision and execution system with specialized volatility roles, deterministic quantitative selection, non-bypassable paper risk controls, broker reconciliation, and audited autonomy.

It now proves—rather than merely claims—when AI inference participated and which Alpaca market-data feed supported each decision. The remaining credibility gap is economic: the fresh competition account still needs broker-confirmed trading activity and P&L.

## Implementation update — 2026-09-02

The audit's two P0 evidence gaps were remediated after this research was written:

- Every `caisheng.decision.v1` record now contains a sanitized `agent_runtime` summary. It distinguishes `deterministic`, `llm_assisted`, `mixed_fallback`, and `deterministic_fallback`, identifies successful and fallback roles, records bounded latency and schema-validation status, and states which financial functions remain deterministic.
- Competition configuration now explicitly requests the `iex` stock feed and `indicative` options feed. The normalized underlying and option snapshots preserve those labels, and each decision shows them beside the actual latest option-quote timestamp. The dashboard no longer implies OPRA/NBBO precision when it has not been configured.

The P1 streaming and operational MCP cross-check items remain deliberate follow-ups. They were not added to the trading path because a late second execution channel or unproven asynchronous state writer would increase operational risk. REST polling and two-way reconciliation remain authoritative.
