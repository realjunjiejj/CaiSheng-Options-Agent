# CaiSheng — Seven-Day Options Alpha Work Plan

**Status:** planning only. This document does not authorize live trading or change the existing implementation.

**Competition objective:** operate an autonomous Alpaca **paper** options agent from a competition account that starts at **$100,000**, generate risk-bounded P&L, and give judges a verifiable explanation of every decision, broker action, and result.

**Product statement:**

> CaiSheng is an event-volatility options capital allocator. It observes an upcoming earnings event, determines whether the option market's implied move is expensive or cheap relative to a point-in-time expected-move distribution, chooses a defined-risk long-vol, short-vol, or no-trade action, executes the approved multi-leg paper order through Alpaca, and independently monitors and closes the position.

---

## 1. What CaiSheng is—and is not

### 1.1 In scope

- US equity options in the Alpaca **paper** environment only.
- Confirmed, scheduled **after-market-close earnings** as the core opportunity set.
- One primary strategy family:
  - long volatility: ATM long straddle;
  - short volatility: defined-risk iron butterfly;
  - abstention: no trade.
- Level 3 Alpaca multi-leg (`mleg`) limit orders for entry and exit.
- Automated scanning, decisioning, execution, reconciliation, monitoring, and reporting.
- Alpaca Trading API as the broker and market-data authority.
- Alpaca MCP server and Alpaca CLI as visibly used integration surfaces.
- A Streamlit cockpit for judges and operators; it observes and controls the runtime but is not the only execution path.

### 1.2 Explicitly out of scope for the seven-day build

- Live-money trading.
- Naked short options, uncovered calls/puts, leverage beyond the defined-risk order itself, martingale sizing, averaging down, or pyramiding.
- 0DTE strategies, intraday high-frequency market making, crypto, copy trading, and a generic all-market agent swarm.
- A second independent strategy sleeve until the first strategy can enter, reconcile, monitor, and exit reliably.
- Online self-tuning of weights during the competition. CaiSheng may log outcomes and shadow alternatives, but must not silently change live trading parameters after losses.

### 1.3 Why this scope maximizes the judging criteria

| Judging criterion | CaiSheng proof |
|---|---|
| P&L performance | Real Alpaca paper orders, actual broker order IDs, open/closed positions, realised and unrealised P&L, and an account-level equity curve. |
| Technology implementation | Direct Alpaca Trading API runtime, official Alpaca MCP calls, Alpaca CLI preflight/reconciliation receipt, immutable decision/order records. |
| Creativity and originality | An adversarial long-vol/short-vol/abstain capital committee plus a shadow counterfactual book that explains alternatives not executed. |
| Presentation and execution | A traceable timeline from live snapshot to agent proposals to deterministic risk gate to broker order to eventual outcome. |

---

## 2. Current code: preserve versus replace

### 2.1 Preserve

The existing project already has valuable components and should remain the base:

- `src/volagent/graph/builder.py`: LangGraph workflow with parallel event/quant and long/short-vol branches.
- `src/volagent/graph/nodes.py`: event, quantitative-volatility, forecast, advocate, critic, strategy, and risk nodes.
- `src/volagent/data/alpaca_sdk.py`: Alpaca live underlying and option-chain normalization.
- `src/volagent/quant/*`: implied move, forecast, Monte Carlo repricing, strategy construction, quote filtering, and deterministic risk checks.
- `src/volagent/execution/alpaca.py`: immutable order-plan fingerprinting and Alpaca multi-leg entry submission.
- `src/volagent/execution/ledger.py`: SQLite approval state and atomic approval consumption.
- Existing unit tests, historical research evaluator, replay scenarios, and UI visualizations.

### 2.2 Replace or extend

| Current behavior | Required CaiSheng behavior |
|---|---|
| UI-only one-unit manual canary | Scheduled autonomous paper runtime governed by a preconfigured mandate. |
| Default strategy NAV can fall back to `$250,000` | Persist initial competition NAV `$100,000`; refresh actual account equity and positions before every order. |
| Ledger knows a broker response succeeded/failed | Ledger supports `SUBMITTING`, `UNKNOWN`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED`, `CLOSED`, and reconciles unknown responses by `client_order_id`. |
| No portfolio state | Account, open orders, positions, reserved risk, sector exposure, daily P&L, drawdown, and trade count are inputs to every allocation. |
| Entry-only order construction | Explicit entry and close order plans, including correct `buy_to_close` / `sell_to_close` intents. |
| MCP tool schemas only | A real configured MCP client/server path with a visible audit record of tool calls. |
| No scheduler or monitor | Durable scheduled scanner, order watcher, position monitor, exit manager, and end-of-day reconciler. |

---

## 3. The exact runtime architecture

```text
Alpaca account / clock / positions / orders / stock quote / option chain
                              │
                    Snapshot and Event Validator
                              │
      ┌───────────────────────┼────────────────────────┐
      │                       │                        │
Event Intelligence       Volatility Quant        Portfolio State Reader
      │                       │                        │
      └───────── Expected-move distribution + IV data ─┘
                              │
                 Long-vol / Short-vol / Abstain proposals
                              │
                          Model Critic
                              │
                 Deterministic Capital + Risk Allocator
                              │
                   Durable Order Intent (SQLite)
                              │
                  Alpaca MLeg Entry Order Submission
                              │
      Broker Reconciliation ← Order/Position Monitor → Exit Manager
                              │
                 Closed-trade record + Shadow Book + UI
```

### 3.1 Ownership rule

Only deterministic Python code may:

- choose final quantity;
- compare risk limits;
- create a broker order;
- submit, cancel, or close a broker order;
- update the portfolio ledger;
- trip or clear a halt.

LLM nodes may explain event evidence and argue for a structure. They cannot create arbitrary ticker symbols, contracts, quantities, prices, or broker actions.

### 3.2 Required modules

| Module | Responsibility | Must never do |
|---|---|---|
| `event_scanner` | Produce a bounded candidate list of confirmed upcoming earnings. | Invent event dates or use unconfirmed events. |
| `snapshot_builder` | Read live Alpaca data and establish a single decision timestamp. | Mix stale/replay data into a live order. |
| `research_graph` | Produce structured long/short/no-trade analysis. | Submit orders. |
| `portfolio_allocator` | Rank eligible proposals using actual account state and reserve risk. | Let an LLM override caps. |
| `order_gate` | Validate mandate, kill switch, freshness, duplicate status, and order topology. | Retry an uncertain broker submission. |
| `broker_reconciler` | Match order intent with Alpaca order/position evidence. | Infer a fill from a missing response. |
| `position_monitor` | Evaluate exits on every open strategy. | Open new risk. |
| `exit_manager` | Construct and submit atomic close plans. | Close a strategy leg-by-leg except under an explicit emergency protocol. |
| `journal_reporter` | Persist receipts and render judge-facing metrics. | Change strategy parameters. |

---

## 4. Trading strategy contract

### 4.1 Opportunity eligibility

An event is eligible only when all conditions pass:

1. Symbol is in the configured liquid US-equity earnings universe.
2. Earnings date, time, and source are confirmed; core mode accepts AMC events only.
3. Event occurs in the future and entry is inside the configured entry window.
4. Alpaca paper market clock reports regular-market trading is open.
5. Underlying bid/ask is finite, positive, uncrossed, and fresh.
6. Both sides of an ATM call/put pair are available with a common expiration.
7. All strategy legs are tradable, have valid quote timestamps, acceptable spread, sufficient volume/open interest, Greeks, and IV.
8. Historical event-move input is verified, strictly before the current event, and sufficient for the model's minimum sample requirement.
9. No current open strategy has the same underlying or unacceptable correlated/sector exposure.
10. Portfolio mandate, daily loss limit, drawdown limit, and kill switch permit a new order.

Failure of any condition produces a `NO_TRADE` decision with a machine-readable reason.

### 4.2 Quantitative decision rule

All values must be calculated from the frozen live snapshot.

```text
implied_move_ask = cost to buy the ATM straddle / spot
implied_move_bid = credit received for the ATM straddle / spot
expected_move     = CaiSheng forecast median absolute move
uncertainty       = forecast uncertainty buffer

long_edge  = expected_move - implied_move_ask
short_edge = implied_move_bid - expected_move
```

Decision order:

1. Reject if forecast is out-of-distribution or below the preconfigured confidence floor.
2. Reject if the critic vetoes the snapshot or evidence.
3. Build and price both eligible structures using conservative executable sides of every option quote:
   - straddle entry at asks;
   - iron-butterfly shorts at bids and wings at asks.
4. Reprice candidates using the existing distribution and include fees/slippage.
5. Select long volatility only if `long_edge > uncertainty` **and** net expected P&L after costs is positive.
6. Select short volatility only if `short_edge > uncertainty`, expected IV crush supports it, net expected P&L after costs is positive, and tail stress loss remains below the hard budget.
7. Otherwise abstain.

The output must include both edges, both candidate scores, the winning decision, and why the losing alternative was rejected.

### 4.3 Initial portfolio mandate

These are starting parameters, not claims of optimality. They are frozen before live operation and changed only with a versioned config change.

| Limit | Initial value | Enforcement |
|---|---:|---|
| Competition starting NAV | `$100,000` | Verified once before first submission; stored as immutable competition metadata. |
| Recommended maximum loss per strategy | `$500` / 0.50% initial NAV | Deterministic sizing target. |
| Absolute maximum loss per strategy | `$1,000` / 1.00% current equity | Hard reject. |
| Maximum open strategies | 3 | Hard reject. |
| Maximum new entries per day | 2 | Hard reject. |
| Maximum risk reserved across open strategies | `$2,000` / 2.00% current equity | Hard reject. |
| Maximum same-sector reserved risk | `$1,000` | Hard reject. |
| Daily realised + unrealised loss halt | `$1,500` | Persistent halt; no new entries. |
| Competition drawdown halt | 5.00% from high-water equity | Persistent halt; no new entries; monitor stays active. |
| Strategy multiplier | 100 | Validate every leg. |
| Short option policy | Only inside exact defined-risk multi-leg structures | Hard reject. |

The current equity may move after the first trade. Only the **starting balance** is exactly `$100,000`; runtime sizing uses fresh Alpaca equity.

### 4.4 Entry plan

For every approved proposal:

1. Read current Alpaca account, positions, and open orders.
2. Recalculate all portfolio caps from the fresh broker state.
3. Re-read strategy-leg quotes; reject if any quote is stale, crossed, or changes beyond the configured tolerance.
4. Generate a deterministic economic fingerprint from strategy ID, event ID, legs, net limit price, quantity, model version, decision timestamp bucket, and mandate version.
5. If an active/recent intent with the same economic fingerprint exists, do not submit again.
6. Generate one `client_order_id` and persist the full intent before the broker call.
7. Submit exactly one `mleg` DAY limit order to the Alpaca paper endpoint.
8. Persist the raw broker response when received.
9. If timeout/network exception/ambiguous response occurs, mark `UNKNOWN`; query Alpaca by the same `client_order_id`; do not create a new ID and do not resend.
10. Reserve strategy risk only after broker acceptance is established; refresh it after fill/cancel/rejection reconciliation.

### 4.5 Exit plan

The monitor evaluates every open strategy on its configured cadence. It must use a close order plan, not reuse the entry plan.

| Strategy | Exit trigger | Atomic close legs |
|---|---|---|
| Long straddle | Profit capture, maximum loss, time exit, or post-event exit time | Sell call `sell_to_close` + sell put `sell_to_close`. |
| Short iron butterfly | Profit capture, maximum loss, time exit, post-event exit time, or safety halt | Buy ATM short call `buy_to_close`, buy ATM short put `buy_to_close`, sell long call wing `sell_to_close`, sell long put wing `sell_to_close`. |

Exit requirements:

- Verify actual broker positions before constructing a close request.
- Use `mleg` order class where the broker supports closing all legs atomically.
- Use current live quotes to calculate a limit price.
- Cancel a stale unfilled closing order, refresh quotes, and create a new close intent linked to the original strategy only after reconciliation.
- If a broker position contradicts CaiSheng's ledger, trip the halt and require explicit operator resolution; do not guess the missing legs.
- A halt blocks **new risk** but allows monitored risk-reducing close/cancel actions under a dedicated path.

---

## 5. Agent graph and outputs

### 5.1 Agent roles

| Node | Type | Input | Output | Authority |
|---|---|---|---|---|
| Snapshot Builder | deterministic | Alpaca data/account/clock | validated snapshot | May reject data only. |
| Event Intelligence | LLM + evidence contract | confirmed event/evidence | `EventMagnitudeAssessment` | Advisory only. |
| Volatility Quant | deterministic | option chain/underlying/history | implied move, RV, surface quality | Computes inputs only. |
| Forecast Engine | deterministic | features/history | move and IV-crush forecasts | Computes forecast only. |
| Long-Vol Advocate | LLM | locked forecast/evidence | `VolatilityThesis` | Advisory only. |
| Short-Vol Advocate | LLM | locked forecast/evidence | `VolatilityThesis` | Advisory only. |
| Critic | LLM + deterministic validations | all proposals/evidence | `CriticReport` | May veto. |
| Portfolio Allocator | deterministic | candidates + broker portfolio | ranked selection, size, rejects | Final allocation authority. |
| Risk Gate | deterministic | selected proposal + mandate | pass/fail checks | Final execution authority. |

### 5.2 Primary output: `DecisionRecord`

Every candidate scan emits one JSON record, including abstentions. This is CaiSheng's main agent output.

```json
{
  "schema_version": "caisheng.decision.v1",
  "decision_id": "dec-20260828-AAPL-01",
  "run_id": "run-...",
  "strategy_version": "caisheng-1.0.0",
  "mode": "alpaca_paper",
  "status": "APPROVED|NO_TRADE|BLOCKED|ERROR",
  "generated_at": "2026-08-28T14:30:00Z",
  "snapshot": {
    "symbol": "AAPL",
    "spot": 0.0,
    "underlying_quote_time": "...",
    "option_snapshot_time": "...",
    "event_id": "...",
    "event_time": "...",
    "event_source_url": "..."
  },
  "volatility_view": {
    "implied_move_bid_pct": 0.0,
    "implied_move_ask_pct": 0.0,
    "expected_move_median_pct": 0.0,
    "q20_pct": 0.0,
    "q80_pct": 0.0,
    "expected_iv_crush_points": 0.0,
    "forecast_confidence": 0.0,
    "out_of_distribution": false
  },
  "proposals": [
    {
      "strategy": "LONG_STRADDLE",
      "executable_edge_pct": 0.0,
      "expected_pnl_dollars": 0.0,
      "max_loss_dollars": 0.0,
      "risk_adjusted_score": 0.0,
      "rejection_reasons": []
    },
    {
      "strategy": "SHORT_IRON_BUTTERFLY",
      "executable_edge_pct": 0.0,
      "expected_pnl_dollars": 0.0,
      "max_loss_dollars": 0.0,
      "risk_adjusted_score": 0.0,
      "rejection_reasons": []
    }
  ],
  "selected_action": "LONG_STRADDLE|SHORT_IRON_BUTTERFLY|NO_TRADE",
  "selected_strategy_id": "...|null",
  "quantity": 0,
  "risk": {
    "mandate_version": "...",
    "current_equity": 0.0,
    "reserved_risk_before": 0.0,
    "reserved_risk_after": 0.0,
    "hard_checks": [],
    "warnings": [],
    "rejection_reasons": []
  },
  "critic": {
    "recommendation": "continue|force_no_trade",
    "warnings": [],
    "failure_reasons": []
  },
  "artifact_hash": "sha256..."
}
```

### 5.3 Other required outputs

| Output | When created | Required contents |
|---|---|---|
| `OrderIntent` | Before every broker write | decision ID, economic fingerprint, `client_order_id`, legs, exact limit, quote snapshots, expiry, risk reservation, state `PENDING_SUBMISSION`. |
| `ExecutionReceipt` | On broker response/reconciliation | Alpaca order ID, client order ID, status, submitted/filled times, filled quantity, average fill, raw response hash. |
| `PositionMonitorReport` | Every monitor cycle | broker position evidence, mark, estimated P&L, exit triggers, current orders, action or no-action. |
| `ClosedTradeRecord` | After strategy is fully closed | entry/exit fills, realised P&L, fees, holding time, forecast, actual move, risk usage, outcome label. |
| `ShadowBookRecord` | After each closed event | selected strategy and non-executed alternatives, realised counterfactual mark-to-market labelled non-executable where quote data is insufficient. |
| `DailyReconciliationReport` | At start/end of each market day | Alpaca account, positions, open orders, ledger differences, halt state, unresolved exceptions. |
| `CompetitionScoreboard` | UI and export | starting NAV, current equity, realised/unrealised P&L, return, drawdown, trade count, win rate, average risk, rejected proposals, open risk. |

### 5.4 Human-readable output example

```text
CAISHENG DECISION — APPROVED
Symbol: AAPL | Event: confirmed AMC earnings
Expected move: 4.8% | Implied buy move: 4.1% | Implied sell move: 3.8%
Long-vol edge: +0.7% | Short-vol edge: -1.0%
Selected: Long Straddle, 1 unit
Maximum loss: $420 | Current portfolio risk after entry: $920 / $2,000
Risk gate: PASS (20/20 hard checks)
Broker action: Alpaca paper MLeg limit order, client_order_id=...
Exit rule: close at post-event evaluation time, profit target, or loss threshold.
```

For an abstention:

```text
CAISHENG DECISION — NO TRADE
Reason: forecast edge does not exceed uncertainty plus executable bid/ask costs.
Long-vol edge: +0.12% vs required +0.55%
Short-vol edge: -0.34% vs required +0.55%
No Alpaca order submitted. Risk reserved: $0.
```

---

## 6. Alpaca, MCP, and CLI implementation plan

### 6.1 Alpaca Trading API: runtime authority

Use the API directly for:

- market clock;
- account equity, cash, buying power;
- open/closed orders;
- positions;
- underlying quotes/bars;
- option chain, contract metadata, quotes, Greeks, IV, volume, and OI;
- multi-leg limit order entry and exit;
- cancel/replace where permitted;
- exact order lookup by `client_order_id` or order ID.

No result from an LLM, Streamlit session, cached object, or replay fixture may override broker state.

### 6.2 Alpaca MCP: judge-visible tool integration

Current `alpaca_mcp.py` contains schemas only. CaiSheng must add a real MCP connection and audit it.

The MCP-enabled agent may use read tools for:

- account summary;
- positions;
- orders;
- current quote;
- option-chain inspection;
- market clock;
- execution-status lookup.

Write tools must not bypass `order_gate`. The MCP write path either:

1. calls the same internal intent/order-gate service as the direct SDK path; or
2. stays disabled and is displayed as a read-only judge-facing integration.

Every MCP call must record tool name, sanitized arguments, timestamp, result status, and correlated `decision_id`; never log credentials.

### 6.3 Alpaca CLI: operations proof

Create two commands/scripts that call the official Alpaca CLI and save sanitized JSON receipts:

1. **Preflight** before the first daily runtime cycle:
   - verify paper endpoint/profile;
   - verify account accessibility;
   - capture equity/cash/buying power;
   - capture open orders/positions;
   - assert initial starting balance metadata exists;
   - fail closed if any check fails.

2. **Reconciliation** after the market close:
   - fetch account, open orders, closed orders, and positions;
   - compare with CaiSheng ledger;
   - list differences;
   - mark the day `CLEAN`, `WARNING`, or `HALTED`.

The dashboard links to these receipts. The CLI is therefore a real part of the system, not a screenshot prop.

---

## 7. Durable state and state transitions

### 7.1 Required persistence

Use SQLite initially. One database is enough for seven days if all writes are transactional and the process is single-instance locked.

Minimum tables:

- `competition_metadata` — competition ID, initial NAV, start timestamp, strategy version.
- `decision_records` — immutable decision JSON and hashes.
- `order_intents` — all intended broker writes and state transitions.
- `broker_orders` — observed Alpaca order evidence.
- `strategies` — composite multi-leg strategy lifecycle and links to entry/exit intents.
- `position_snapshots` — periodic broker state used by monitor/reconciliation.
- `portfolio_snapshots` — equity, cash, buying power, daily P&L, drawdown, reserved risk.
- `halts` — persistent halt reason, scope, timestamp, cleared-by metadata.
- `mcp_audit_events` — sanitized MCP usage proof.

### 7.2 Entry-order state machine

```text
DRAFT
→ RISK_APPROVED
→ INTENT_PERSISTED
→ SUBMITTING
→ ACCEPTED | UNKNOWN | REJECTED
→ PARTIALLY_FILLED | FILLED | CANCELED
```

Rules:

- `INTENT_PERSISTED` is written before the first Alpaca call.
- `UNKNOWN` means the system must reconcile using the same `client_order_id`.
- `UNKNOWN` cannot move back to `SUBMITTING` with a new ID.
- `FILLED` creates/updates exactly one strategy record.
- `REJECTED`/`CANCELED` release reserved risk after broker evidence is verified.

### 7.3 Strategy state machine

```text
PROPOSED
→ ENTRY_PENDING
→ OPEN
→ EXIT_PENDING
→ CLOSED

OPEN → HALTED_RECONCILIATION_REQUIRED
ENTRY_PENDING → CANCELED
EXIT_PENDING → HALTED_RECONCILIATION_REQUIRED
```

### 7.4 Kill switch

Persisted sentinel plus database state. It is checked before every new entry.

Trip on:

- daily/total drawdown threshold;
- data validation failure during an active order transition;
- ledger/broker contradiction;
- duplicate submission attempt;
- invalid account/position response;
- explicit operator action.

The halt blocks entries; it does not abandon existing risk. The monitor continues to reconcile and execute risk-reducing exits.

---

## 8. Test plan and acceptance criteria

### 8.1 Unit tests

Add tests for each invariant below.

| Area | Required test |
|---|---|
| Starting balance | First-run bootstrap accepts only configured `$100,000`; later runs use broker equity without reasserting `$100,000`. |
| Sizing | Cannot size from default `$250,000`; stale/missing account state rejects order. |
| Duplicate prevention | Same economic fingerprint and active intent cannot create a second broker submission. |
| Unknown response | Timeout after broker submission causes reconciliation lookup; retry is prohibited. |
| Close intents | Long straddle and iron-butterfly exits use correct closing position intents. |
| Portfolio caps | Three open strategies, sector cap, daily loss, and drawdown halt all reject new orders. |
| MLeg topology | Exact leg count, common underlying, common expiry, position intents, multiplier, and debit/credit conventions are validated. |
| Quote safety | Non-finite, negative, crossed, stale, or future-dated quotes reject order. |
| Halt persistence | Process restart keeps halt active until explicit clearance. |
| MCP | Tool call audit does not contain secrets and writes cannot bypass order gate. |

### 8.2 Integration tests with mocked Alpaca client

- Clean order lifecycle: approved → accepted → filled → monitored → closed.
- Broker rejects entry due to buying power.
- API response timeout but later lookup returns accepted order.
- Partial fill and deadline cancellation.
- Restart while entry is `SUBMITTING`.
- Broker returns a position not represented in the ledger.
- Market closed prevents new entries.
- Exit monitor submits the correct close request.
- Two concurrent scheduler invocations race for the same event; only one owns the intent.

### 8.3 Paper-account smoke tests

No production-scale trade is needed before these pass:

1. Read-only preflight: account, clock, positions, orders, one live option chain.
2. Dry-run: generate decision/output and full order intent, but submit nothing.
3. One-unit entry canary: only if the competition rules allow it and risk gate passes.
4. Reconcile broker order by `client_order_id`.
5. Run monitor once against the accepted/filled order.
6. Test close lifecycle in paper mode using a valid controlled position.
7. Generate daily reconciliation and verify that dashboard values match Alpaca.

### 8.4 Definition of done before enabling autonomous entries

Autonomous entry is disabled until all are true:

- tests pass;
- account is verified as paper-only;
- competition metadata records `$100,000` starting NAV;
- preflight is `CLEAN`;
- scheduler lock works;
- order intent/recovery works;
- monitor can close a controlled paper strategy;
- dashboard reconciles to Alpaca account state;
- kill switch works across process restart;
- no direct UI button bypasses order gate.

---

## 9. Seven-day execution sequence

### Day 0 / immediately: freeze scope and establish evidence

1. Confirm competition account, starting balance, permitted products, autonomous-order policy, and Level 3 options capability.
2. Rename user-facing product language to **CaiSheng** only after a branch/backup is established; preserve Python package paths until runtime is stable.
3. Write `competition_metadata` with initial NAV `$100,000`, strategy version, mandate version, and start time.
4. Install/configure official Alpaca paper-trading/backtesting skills; document the exact CLI profile used.
5. Run read-only Alpaca API, MCP, and CLI preflight.

**Exit criterion:** all three Alpaca surfaces can read the same paper account without exposing credentials.

### Day 1: correct execution primitives

1. Add economic fingerprint and active-intent deduplication.
2. Extend ledger state machine and migrations.
3. Implement `UNKNOWN` broker-response recovery by exact `client_order_id`.
4. Implement real broker order/position reconciliation.
5. Correct position-intent mapping and build close-plan types.
6. Add tests for duplicate, timeout, and closing intents.

**Exit criterion:** entry and close plans are correct without UI involvement.

### Day 2: portfolio mandate and autonomous order gate

1. Add portfolio snapshot reader and use real account equity/positions everywhere.
2. Replace `$250,000` fallback in execution path with fail-closed broker state.
3. Add reserved-risk, daily-loss, drawdown, trade-count, and sector-exposure checks.
4. Add persistent kill switch and single-runtime lock.
5. Add mandate config and version it into every decision.

**Exit criterion:** a valid trade can be accepted; an over-limit trade is deterministically rejected with a receipt.

### Day 3: lifecycle runtime

1. Build event scanner with confirmed earnings source contract.
2. Add scheduled scan cadence and entry cutoff.
3. Add order watcher for open/partial/canceled/filled states.
4. Add position monitor cadence and exit trigger engine.
5. Add closed-trade and daily-reconciliation reporters.

**Exit criterion:** a controlled paper strategy can complete entry → monitor → close → P&L record.

### Day 4: agent and strategy quality

1. Rename graph-facing descriptions from Track 2/VolAgent to CaiSheng/Options Alpha.
2. Ensure all agent proposals are typed and include executable edge, costs, risk, and invalidation.
3. Add portfolio allocator ranking across eligible event candidates.
4. Keep the strategy family fixed; tune only predeclared thresholds using training data, never the new competition results.
5. Add shadow-book records for every selected and rejected structure.

**Exit criterion:** one scan produces ranked candidates and exactly one of long-vol, short-vol, or abstain per candidate.

### Day 5: Alpaca technology proof and cockpit

1. Wire actual Alpaca MCP calls and sanitized audit events.
2. Implement CLI preflight/reconciliation scripts and artifact export.
3. Replace table-first UI with one decision timeline, account panel, risk panel, open positions, and trade journal.
4. Add direct links/identifiers for Alpaca order evidence.

**Exit criterion:** a judge can trace an order from agent decision to Alpaca receipt in under one minute.

### Day 6: controlled paper operation

1. Start in dry-run mode for a complete market cycle.
2. Compare all decision/order/position data with Alpaca.
3. Enable only low-risk autonomous paper entries if preflight and health checks are clean.
4. Do not parameter-chase after every result.
5. Generate end-of-day report and resolve all reconciliation exceptions.

**Exit criterion:** no unresolved ledger/broker differences and all P&L fields reconcile.

### Day 7: judge package

1. Freeze code/config version and run full tests.
2. Export final competition scoreboard, daily receipts, and sample decision trace.
3. Write the one-page required summary: AI logic, risk gates, Alpaca API/MCP/CLI implementation, limitations, and actual paper results.
4. Rehearse demo:
   - account preflight;
   - candidate scan;
   - agent disagreement;
   - risk decision;
   - Alpaca order lifecycle;
   - P&L and shadow-book outcome.

---

## 10. Judge-facing screens and demo script

### 10.1 Home / Capital Command screen

Show first:

- starting NAV `$100,000`;
- current equity and daily/total P&L;
- realised/unrealised P&L;
- reserved maximum loss and remaining risk capacity;
- halt status;
- Alpaca connectivity status;
- current graph/runtime health;
- open strategies and their next planned action.

### 10.2 Decision timeline screen

For one trade or abstention:

```text
14:05:00  Alpaca snapshot frozen
14:05:01  Volatility Quant: implied move 4.1%
14:05:02  Long-Vol Advocate: supports long volatility
14:05:02  Short-Vol Advocate: rejects short volatility
14:05:03  Critic: PASS
14:05:03  Portfolio Allocator: 1 unit, $420 maximum loss
14:05:03  Order Intent persisted (hash...)
14:05:04  Alpaca MLeg submitted (client_order_id...)
14:05:05  Broker accepted (order_id...)
```

### 10.3 Closed-trade screen

Show:

- entry and exit order IDs;
- actual fills and timestamps;
- realised P&L;
- pre-event expected/implied/realised move;
- original risk cap versus actual loss/gain;
- selected strategy versus shadow alternatives;
- whether the forecast/IV-crush assumption was directionally correct.

### 10.4 One-page write-up outline

1. One-sentence product claim.
2. Decision logic: event → IV/move comparison → long/short/abstain.
3. Agent roles and why the deterministic allocator has final authority.
4. Risk gates and hard limits.
5. Alpaca Trading API, MCP, and CLI roles.
6. Actual paper results and transparent limitation statement.

---

## 11. Non-negotiable integrity rules

- Never describe a replay, synthetic simulation, bar proxy, or shadow trade as Alpaca paper P&L.
- Never represent forecast confidence as empirically calibrated unless calibration results support it.
- Never hard-code a favored ticker, including NVDA, into live selection logic.
- Never submit an order based on expired, stale, crossed, invalid, or mixed-mode quotes.
- Never let an LLM write raw broker parameters or bypass the deterministic order gate.
- Never retry a potentially accepted order with a new `client_order_id`.
- Never silently drop an event, order, position, or reconciliation failure; surface it as `BLOCKED`, `WARNING`, or `HALTED`.
- Never alter risk parameters without a versioned configuration receipt.
- Never claim that P&L is guaranteed or that paper performance predicts live performance.

---

## 12. First build instruction after this plan is approved

Implement in this exact order:

1. durable order intent + unknown-response reconciliation;
2. correct multi-leg close-plan construction;
3. broker position/order monitor and daily reconciliation;
4. portfolio mandate using real Alpaca account state and `$100,000` competition metadata;
5. autonomous scheduler/runtime;
6. actual MCP and CLI audit integration;
7. CaiSheng renaming and judge cockpit.

Do not begin with additional agents, new strategies, or cosmetic UI work.
