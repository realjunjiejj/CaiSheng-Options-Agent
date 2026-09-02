# CaiSheng 10/10 Remediation Agent Prompt

Copy the instructions below into the coding agent responsible for repairing CaiSheng. The agent may also read this file directly.

---

## Mission

You are the principal engineer, adversarial tester, quantitative developer, and release controller for:

`/Users/yanjunjie/Documents/Alpaca`

Your objective is to repair CaiSheng until it is genuinely ready for an independent hackathon-judge re-audit.

Do not merely make existing tests pass. Do not declare success based on test quantity. Prove that the real application boundaries work.

## 1. Mandatory documents

Before modifying code, read these files completely:

1. `audit.md`
2. `MILESTONE_STATUS.md`
3. `CORRECTIONS.md`
4. `CAISHENG_WORKPLAN.md`
5. `CAISHENG_JUDGE_SUMMARY.md`
6. `README.md`

In `audit.md`, locate this heading:

`# CaiSheng — Independent Post-Remediation Adversarial Re-audit`

Treat that section and every `CAI-R3-*` finding as the current authoritative defect list. It supersedes all previous PASS claims.

Immediately change the controller state to:

```text
Controller state: REMEDIATION_IN_PROGRESS
GLOBAL_SUCCESS: FALSE
Current milestone: R3-P0 remediation
```

Do not set `GLOBAL_SUCCESS: TRUE` yourself. When every mocked and read-only requirement passes, set:

```text
Controller state: READY_FOR_INDEPENDENT_REAUDIT
GLOBAL_SUCCESS: FALSE
```

Independent review and an explicitly authorized Alpaca paper canary are required before global success.

## 2. Non-negotiable safety restrictions

Never:

- Submit, replace, cancel, or close an Alpaca paper order without fresh, explicit user authorization for that specific canary.
- Connect to a live-money Alpaca endpoint.
- Enable real-money trading.
- Print, log, commit, or expose API credentials.
- Invent live quotes, IV, Greeks, strikes, expiration dates, event sources, account balances, fills, positions, or P&L.
- Treat replay or synthetic execution as Alpaca paper execution.
- Weaken a safety check merely to make a test pass.
- Delete or overwrite unrelated user changes.
- Commit or push unless explicitly instructed.
- Claim predictive alpha or profitable performance without statistically defensible evidence.
- Catch a critical exception and return a misleading successful status.

All broker behavior during remediation must use mocks, fakes, or read-only Alpaca calls.

## 3. Required development loop

For every defect:

1. Reproduce it with a failing behavioral test.
2. Confirm the test fails for the expected reason.
3. Diagnose the actual root cause.
4. Implement the smallest integrated repair.
5. Run the focused test.
6. Run all related subsystem tests.
7. Run the entire test suite.
8. Run compilation and repository hygiene checks.
9. Append a detailed entry to `CORRECTIONS.md`.
10. Update `MILESTONE_STATUS.md` honestly.
11. Continue to the next defect.

Do not stop because a repair attempt fails. Diagnose, patch, and rerun.

Only stop early when:

- an action requires explicit paper-order authorization;
- credentials or an external service are unavailable and no safe mocked or read-only alternative exists;
- a material requirement is ambiguous and different interpretations would fundamentally change the architecture.

Ordinary test failures, difficult bugs, or implementation complexity are not stopping conditions.

## 4. First action: install the missing adversarial tests

Create a permanent repository test module such as:

`tests/adversarial/test_r3_end_to_end_acceptance.py`

Reproduce all eight independent failures described in `audit.md`:

1. The autonomous runner generates a decision for an eligible event.
2. A replay DecisionRecord uses `replay_synthetic` provenance.
3. Every graph decision is persisted in SQLite.
4. Actual MCP discovery includes `alpaca_get_option_chain`.
5. A valid MCP write request does not produce an internal schema error.
6. The broker gateway rejects an entry at the maximum open-strategy limit.
7. A triggered simulated close completes and persists realized P&L.
8. Missing event-source evidence is rejected rather than fabricated.

These tests must exercise public orchestration boundaries. Do not test only isolated helpers.

Keep the tests failing until the corresponding behavior is genuinely fixed.

## 5. P0 repairs — complete in this exact order

### P0-A: Repair the autonomous lifecycle

Correct `LifecycleRunner` so it:

- imports `VolAgentWorkflow` from the real module;
- constructs the workflow with its actual supported arguments;
- invokes `workflow.run()` with a valid state dictionary;
- passes the eligible event, symbol, data mode, portfolio snapshot, market adapter, historical information, and shared dependencies correctly;
- uses the same `ExecutionLedger` as the lifecycle;
- does not create hidden independent ledgers inside graph nodes;
- records decision-generation failures explicitly;
- never reports `CLEAN` merely because an exception was swallowed;
- sets `decisions_generated` only after a valid graph result exists;
- distinguishes decisions, abstentions, rejected entries, and submitted entries.

Add behavioral assertions for:

- one eligible event produces exactly one durable decision record;
- a graph exception produces cycle status `ERROR` or `HALTED`;
- no eligible event produces a valid no-op;
- multiple eligible events are all analyzed before allocation;
- no submission occurs when the global submission switch is disabled.

### P0-B: Create one non-bypassable broker-write gateway

UI, lifecycle, MCP, and CLI must all use the same gateway.

Remove any per-instance argument capable of overriding a disabled global submission switch.

The gateway must require, at execution time:

- `BrokerTarget.ALPACA_PAPER`;
- paper endpoint confirmation;
- enabled global submission policy;
- a fresh authenticated account snapshot;
- matching competition account ID;
- an immutable persisted DecisionRecord;
- a matching approved strategy;
- a valid approval policy;
- an unexpired approval token;
- immutable fresh quote snapshots for every exact contract;
- no crossed, negative, stale, future, or non-finite quotes;
- verified event source and event timing;
- a passing strategy risk gate;
- a passing portfolio mandate gate;
- an atomic durable risk reservation;
- a valid order fingerprint;
- duplicate-exposure protection;
- valid contract symbols and expirations;
- sufficient buying power;
- system-halt enforcement for entries.

The gateway must reconstruct or receive the real candidate. It must never call the portfolio gate with `candidate=None` for a new entry.

Prove rejection for:

- maximum open strategies;
- maximum daily entries;
- per-strategy loss breach;
- aggregate risk breach;
- same-sector risk breach;
- insufficient buying power;
- stale portfolio state;
- missing approval;
- missing decision record;
- mismatched decision ID;
- duplicate exposure;
- disabled submission switch.

Risk-reducing closes may proceed during an entry halt, but must retain quote, position, fingerprint, and accounting checks.

### P0-C: Repair the complete close lifecycle

Fix every broken import and domain-model mismatch.

Implement this actual flow:

```text
filled entry
→ exact strategy contract lookup
→ fresh exit quotes
→ exit trigger
→ closing plan
→ close approval
→ broker or simulator submission
→ fill confirmation
→ strategy CLOSED
→ risk reservation released
→ realized P&L persisted
→ reconciliation clean
```

Requirements:

- Match positions using exact OCC contract symbols stored in the entry plan.
- Never group every position sharing an underlying.
- Obtain fresh quotes for each closing leg.
- Preserve correct buy-to-close and sell-to-close intents.
- Permit risk-reducing closes under an entry halt.
- Handle partial or asymmetric fills fail-closed.
- Do not mark a cancellation or close complete until broker confirmation.
- Use actual fill prices for realized P&L.
- Include commissions and slippage.
- Transition the entry strategy to `CLOSED`.
- Release reserved portfolio and sector risk atomically.
- Make repeated close processing idempotent.

Add a true orchestration test. Do not substitute a direct call to `ClosedTradeReporter`.

### P0-D: Rebuild MCP integration around canonical services

Keep the real MCP server, but repair the tool surface.

Requirements:

- Register `alpaca_get_option_chain`.
- Verify that it appears through actual `server.list_tools()`.
- Test tool invocation through the MCP server boundary, not only `handle_tool_call`.
- Make the write tool use the canonical order-building and broker-gateway services.
- Never manually construct fake `ApprovedLegSnapshot` objects from a parent limit price.
- Fetch or receive immutable real contract snapshots.
- Use the correct `OrderPlan` schema.
- Do not mutate frozen Pydantic objects.
- Use a real five-minute expiry.
- Require a persisted decision ID and approval.
- Return structured `SUCCESS`, `REJECTED`, or `ERROR` results.
- Preserve MCP call ID, decision ID, sanitized arguments, outcome, and receipt linkage.
- Deeply redact credentials from nested inputs and outputs.

Prove an enabled MCP write reaches the mocked broker only when every gate passes. Prove all other routes fail closed.

### P0-E: Repair DecisionRecord durability and provenance

Requirements:

- Correct Pydantic-object access in `record_decision_record`.
- Persist every `APPROVED`, `NO_TRADE`, `BLOCKED`, and `ERROR` decision.
- Use `state["mode"]`, not an incorrect `data_mode` key.
- Replay must say `replay_synthetic`.
- Historical bar replay must state its exact historical or proxy mode.
- Live read-only must say `live_read_only`.
- Alpaca paper must appear only after genuine paper execution.
- A persistence failure must change the run to explicit `ERROR`; it must not be warning-only.
- Use the shared injected ledger.
- Verify the stored hash by reading the record back.
- Ensure decision IDs remain collision-resistant under concurrent runs.

## 6. P1 repairs

### Persistent portfolio authority

Implement and test:

- persistent competition account ID;
- current account-ID matching during preflight and execution;
- persistent HWM across restarts;
- persistent daily portfolio snapshots;
- accurate daily P&L semantics;
- deposit/withdrawal handling or explicit fail-closed detection;
- broker-derived positions combined with ledger-derived strategy reservations;
- no self-verification of starting NAV using only hardcoded metadata.

Preflight must distinguish:

- authenticated current equity;
- configured competition starting balance;
- persisted competition metadata;
- account identity;
- current drawdown and HWM.

### Integrate the portfolio allocator

`PortfolioAllocator` must be called by the real multi-event lifecycle.

Required flow:

```text
scan all events
→ run all eligible analyses
→ collect approved candidates
→ rank using executable risk-adjusted edge
→ apply portfolio capacity
→ atomically reserve risk
→ submit selected entries
→ record explicit rejection for unselected candidates
```

Selection must be deterministic for equal inputs.

### Exchange-aware event scheduling

Use Alpaca's market clock/calendar or a reliable exchange-calendar implementation.

Handle:

- weekends;
- holidays;
- early closes;
- daylight-saving transitions;
- next valid exit session;
- entry windows relative to the actual session close.

Require a verified source URL. Never construct `https://ir.<symbol>.com`.

### Cancellation lifecycle

Use a non-terminal cancellation state such as `CANCEL_REQUESTED` or `CANCEL_PENDING`.

Only mark an order `CANCELED` after Alpaca confirms it.

If:

- no supported cancellation method exists;
- the request fails;
- status cannot be confirmed;
- the broker is unreachable;

transition to `UNKNOWN`, schedule reconciliation, and block duplicate exposure.

### Honest deterministic versus LLM behavior

- Preserve deterministic fallbacks.
- Clearly label every run as deterministic or LLM-backed.
- Do not imply the critic is LLM-backed when it ignores `llm_client`.
- Either implement structured LLM critic output with deterministic validation or label the critic deterministic.
- The safety governor must remain deterministic and cannot be overridden by an LLM.
- LLM failure must fall back safely or force `NO_TRADE`.

## 7. P&L and quantitative evidence

Do not optimize only forecast MAE. The competition judges P&L.

Preserve the existing no-look-ahead historical evaluation, but add honest strategy-level evaluation:

- net option P&L;
- transaction costs;
- conservative fill assumptions;
- maximum drawdown;
- Sharpe or another return/risk ratio when sample size permits;
- win rate;
- average win and loss;
- profit factor;
- turnover;
- exposure;
- abstention rate;
- tail loss;
- performance by ticker and regime;
- performance against naive baselines;
- bootstrap confidence intervals;
- sensitivity to spreads and slippage.

Required baselines:

- no trade;
- always long straddle;
- always short defined-risk volatility;
- implied-move forecast;
- historical-median forecast;
- agent without risk governor;
- agent without multi-agent debate.

The current evidence does not prove alpha. Never conceal that the current agent MAE and RMSE are worse than the implied-move baseline.

Use language such as:

```text
Historical proxy evaluation, not executable-fill proof.
Statistically unproven until confidence intervals exclude zero.
Competition P&L comes only from Alpaca paper-account receipts.
```

Do not tune against revealed OOS outcomes and continue calling the same sample out-of-sample. Create a new sealed holdout if those results influence model changes.

## 8. CaiSheng presentation and branding

Replace judge-facing references to:

- `VolAgent Alpha`
- `Track 2`
- `Track 02`

with:

- `CaiSheng`
- `Options Alpha Agents`

Internal Python package names may remain `volagent` if renaming them risks regressions, but user-facing branding must be consistent.

Update:

- README title and narrative;
- application title and navigation;
- CLI output;
- configuration display names;
- research page;
- scoreboard;
- cockpit;
- comments or labels visible during the demonstration.

The 60-second judge flow must show:

1. Authenticated $100,000 Alpaca paper account.
2. Current market and event inputs with timestamps.
3. Implied versus expected move.
4. Long-vol and short-vol theses.
5. Critic and deterministic risk-gate verdicts.
6. Selected structure or explicit `NO_TRADE`.
7. Maximum loss and portfolio risk reservation.
8. Alpaca API, MCP, and CLI integration evidence.
9. A broker receipt or clearly labeled replay receipt.
10. Competition P&L and drawdown without unsupported claims.

Keep the UI concise. Prioritize:

- equity and P&L curve;
- payoff diagram and break-evens;
- implied-versus-expected move;
- risk-budget utilization;
- decision trace;
- positions, orders, and reconciliation;
- baseline comparison.

## 9. Mandatory acceptance suite

Before requesting re-audit, all of these commands must pass:

```bash
uv run pytest -q
uv run pytest -q tests/adversarial/test_r3_end_to_end_acceptance.py
uv run pytest -q tests/unit/test_ui_rendering.py
uv run pytest -q tests/unit/test_alpaca_cockpit.py
uv run python -m compileall -q src app.py cli.py
git diff --check
```

Also prove:

- zero unexpected skips;
- zero expected failures hiding defects;
- no warnings caused by CaiSheng code;
- no secret-like values in tracked files;
- no accidental live endpoint;
- no source files silently omitted from Git;
- dependency lockfile is current;
- startup works from a clean environment;
- MCP discovery and mocked tool invocation work;
- CLI preflight fails closed without credentials;
- CLI reconciliation does not present a clean zero-state result as proof of a completed trade;
- the autonomous mocked lifecycle completes a full round trip;
- all eight independent R3 acceptance failures are repaired.

Do not require a perfectly clean working tree if the user's changes are intentionally uncommitted. Report exact `git status`; never describe `git diff --check` as a “clean Git diff.”

## 10. Correction records

For every repair, append to `CORRECTIONS.md`:

- correction ID;
- severity;
- root cause;
- files changed;
- behavior before;
- behavior after;
- failing test added;
- focused test command and result;
- full-suite command and result;
- remaining limitation.

Do not edit an old audit verdict to hide it. Append new evidence.

## 11. Completion conditions

You may set:

```text
Controller state: READY_FOR_INDEPENDENT_REAUDIT
GLOBAL_SUCCESS: FALSE
```

only when all these conditions are true:

- all existing tests pass;
- all R3 acceptance tests pass;
- the autonomous runner invokes the actual LangGraph;
- portfolio limits are enforced at the final broker-write boundary;
- the mocked entry-to-close lifecycle succeeds;
- MCP discovery and a mocked valid write succeed;
- decisions persist with truthful provenance;
- portfolio HWM and account binding survive restart;
- the allocator is wired into the real lifecycle;
- calendar and event sources are authoritative;
- branding is complete;
- UI renders successfully;
- no unsupported P&L or alpha claims remain;
- no paper or live broker write occurred during remediation.

Then stop and ask for:

1. an independent code re-audit;
2. explicit authorization for one defined-risk, one-unit Alpaca paper canary.

Do not execute that canary automatically.

A final 10/10 claim requires:

- independent re-audit PASS;
- an explicitly authorized paper canary;
- broker-confirmed entry and exit receipts;
- correct realized P&L;
- clean reconciliation;
- presentation evidence derived from those receipts.

## 12. Final response format

When ready for re-audit, report:

1. Overall state: `READY_FOR_INDEPENDENT_REAUDIT`
2. Findings repaired
3. Files changed
4. Tests added
5. Exact command results
6. Mocked lifecycle evidence
7. MCP evidence
8. Remaining quantitative limitations
9. Paper-canary status: `NOT RUN — AWAITING EXPLICIT AUTHORIZATION`
10. Exact request for independent review

Do not say `10/10`, `production grade`, `alpha proven`, or `GLOBAL_SUCCESS: TRUE` unless every corresponding evidence requirement has been satisfied.

