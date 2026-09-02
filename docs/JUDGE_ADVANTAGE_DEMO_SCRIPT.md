# CaiSheng — Judge-Facing Advantage Demo Script

> **Superseded:** Use [`JUDGE_LIVE_DEMO_SCRIPT.md`](JUDGE_LIVE_DEMO_SCRIPT.md). It contains the post-incident Risk Envelope, full-account P&L policy, and current safe live-demo decision tree. This older script is retained only as historical drafting material.

## Purpose

This is the primary seven-minute presentation script for CaiSheng. It is organized around the competition’s four judging criteria: P&L Performance, Technology Implementation, Creativity & Originality, and Presentation & Execution. For a strict 90-second slot, use `docs/DEMO_SCRIPT.md`; a 30-second fallback is also included below.

The presenter must distinguish three kinds of evidence:

- **Live Alpaca evidence:** current paper-account state, fresh market data, broker orders, positions, and reconciliation.
- **Sealed replay evidence:** historical or synthetic scenarios used to demonstrate agent behavior and safety.
- **Engineering evidence:** tests, immutable receipts, MCP audits, and deterministic invariants.

Never describe replay P&L as live Alpaca P&L or proof of predictive alpha.

---

## Pre-demo setup

Before recording or presenting:

1. Open CaiSheng and select `01 Command`.
2. Confirm the application displays `PAPER ONLY · FAIL CLOSED`.
3. Run **Verify Official Alpaca Lockbox** and confirm all four indicators pass.
4. Run **Run CaiSheng Preflight**.
5. Run **Verify Guarded MCP**.
6. Run **Reconcile Alpaca** if the account contains orders or positions.
7. Confirm no API key, secret key, or account ID is visible.
8. Decide whether the demo will show:
   - a previously completed Alpaca paper trade;
   - a currently eligible live canary analysis without submission; or
   - a fail-closed abstention.
9. Keep the sealed replay available as the reliable demonstration path if markets or event data are unavailable.

Do not enable order submission solely for the presentation.

---

## 0:00–0:35 — The problem and our advantage

**Screen:** `01 Command`

**Judging criteria:** Creativity, Presentation

**Narration:**

> “Most AI trading demos produce a recommendation and stop. CaiSheng is different: it is an autonomous, volatility-focused options system that connects research, debate, deterministic risk, Alpaca paper execution, reconciliation, and performance evidence in one auditable lifecycle.”
>
> “The strategy does not need to predict whether a stock rises or falls. It asks a more testable question: is the absolute move and volatility priced by the option market too high or too low? It can choose a long straddle, a defined-risk short iron butterfly, or no trade.”

**Point to:**

- `CaiSheng` and the `$100,000 PAPER MANDATE` label.
- The four workspaces: Command, Agent, Paper Trade, Evidence.
- `PAPER ONLY · FAIL CLOSED`.

**Key advantage:** The system optimizes for selective, non-directional options alpha rather than forcing a directional prediction or a trade on every scan.

---

## 0:35–1:45 — Real Alpaca API integration

**Screen:** `01 Command`

**Judging criteria:** Technology Implementation, P&L Performance

**Narration:**

> “This Command screen is backed by the Alpaca Trading API. Current equity and buying power come from the authenticated paper account—not from replay fixtures. The competition baseline is fixed at one hundred thousand dollars, and realized performance is measured against that mandate.”
>
> “CaiSheng also reads the Alpaca market clock, stock quotes, option-chain snapshots, positions, and orders. For an eligible trade, it constructs Alpaca Level-3 multi-leg limit orders with exact option symbols and position intents. It never sends market orders and never silently falls back from paper to live money.”

**Action:** Click **Run CaiSheng Preflight**.

**Narration while showing the receipt:**

> “Preflight verifies paper mode, credential-backed account accessibility, positive finite equity, nonnegative buying power, the one-hundred-thousand-dollar competition mandate, and the persistent halt state. If any check fails, the system halts instead of inventing a connection.”

**Action:** Click **Reconcile Alpaca**.

**Narration:**

> “Reconciliation compares both directions: broker orders and positions against the local execution ledger, and ledger intents against Alpaca. Orphaned or unknown states are surfaced instead of being assumed filled.”

**Key advantages:**

- Authenticated Alpaca paper-account state.
- Fresh underlying and option-chain market data.
- Level-3 `mleg` limit-order construction.
- Exact-contract position management.
- Idempotent client-order IDs and timeout reconciliation.
- Actual Alpaca paper P&L remains separate from replay results.

---

## 1:45–2:40 — Alpaca Technology Lockbox

**Screen:** `01 Command`

**Judging criterion:** Technology Implementation

**Action:** Click **Verify Official Alpaca Lockbox**.

**Narration:**

> “This is our Alpaca Technology Lockbox: a proof bundle, not an Alpaca product name. It verifies three official Alpaca agent interfaces live. The official agent-first CLI runs diagnostics plus read-only account and market-clock calls, and must resolve the exact paper endpoint. The official Alpaca MCP Server V2 is launched with an explicit paper flag, discovers its tools dynamically, and performs a real market-clock call.”
>
> “For the judge proof, the official MCP server is restricted to the `assets` and `options-data` toolsets. The entire trading toolset is absent. That means this sponsor-facing proof cannot submit, replace, cancel, close, or exercise anything.”
>
> “The repository also includes Alpaca’s official backtest, paper-trading, CLI, and MCP agent skills with SHA-256 fingerprints. This proves we are not merely calling an endpoint—we built CaiSheng around Alpaca’s intended agent ecosystem.”

**Action:** Click **Verify Guarded MCP**.

**Narration:**

> “This second check is CaiSheng’s own seven-tool FastMCP gateway. Unlike the read-only official MCP proof, it includes guarded multi-leg submission. An AI client cannot manufacture raw order legs: it must provide an existing one-time approval token and matching immutable DecisionRecord ID. The canonical order is loaded from the ledger and routed through the same non-bypassable broker gateway as every other submission.”
>
> “All MCP arguments are recursively sanitized before audit persistence, and the judge view omits account identifiers and raw broker payloads. Streamable HTTP is available at `/mcp`, with legacy SSE for compatible clients.”

**Optional terminal cutaway:**

```bash
python cli.py --lockbox --output-json
python cli.py --preflight --output-json
python cli.py --reconcile --output-json
```

**Narration:**

> “The first command returns one sanitized Lockbox receipt for the official CLI, official MCP V2, official skills, and the locked order boundary. The next two expose CaiSheng preflight and reconciliation as machine-readable receipts.”

**Key advantage:** Alpaca’s official CLI, MCP V2, skills, Trading API, and Market Data API are visibly used, while only one CaiSheng gateway can mutate the paper account.

---

## 2:40–4:00 — Multi-agent reasoning plus mathematical rigor

**Screen:** `02 Agent`

**Judging criteria:** Creativity, Technology Implementation

**Narration:**

> “This is a sealed replay. It is intentionally isolated from the Alpaca ledger and can execute only in a local simulator.”

**Action:** Select a featured scenario.

**Narration:**

> “The LangGraph contains nine explicit stages. It initializes the run, freezes a point-in-time market snapshot, analyzes event magnitude and volatility in parallel, produces a calibrated move forecast, runs long-vol and short-vol advocates in parallel, sends both to an independent model-risk critic, and finally applies deterministic strategy and risk logic.”
>
> “This receipt states whether each reasoning role used structured LLM inference, deterministic synthesis, or a validated fallback. I only claim LLM participation when the receipt says `LLM_ASSISTED`. In every mode, deterministic code computes the option-implied move, empirical expected-move distribution, IV-crush estimate, expected P&L, Greeks, stress losses, maximum loss, and executable edge after spread and slippage.”

**Point to:**

- Implied move versus forecast move.
- Long-vol and short-vol theses.
- Exact contract symbols, strikes, expiration, sides, and assumed prices.
- Payoff curve and break-even points.
- Dynamically derived risk-gate result.

**Narration:**

> “This neuro-symbolic split is a major advantage. Language models add contextual reasoning and adversarial debate, while deterministic math controls everything that can lose money.”

---

## 4:00–5:25 — Risk management and autonomous restraint

**Screen:** `02 Agent`, then `03 Paper Trade`

**Judging criteria:** P&L Performance, Creativity

**Narration:**

> “CaiSheng’s goal is not maximum trade count. It is maximum quality per unit of risk. Every candidate faces a twenty-point deterministic gate covering paper-only execution, event confirmation, model confidence, data consistency, defined-risk topology, independently recomputed maximum loss, stress loss, delta exposure, liquidity, quote freshness, common expiration, leg ratios, and critic approval.”
>
> “Portfolio gates then enforce one-percent maximum loss per strategy, two-percent aggregate reserved risk, position and daily-entry limits, sector concentration, buying power, a daily-loss halt, and a high-water-mark drawdown halt.”

**Action:** Move to `03 Paper Trade`.

**Narration:**

> “The live canary refuses replay contracts. It requires a confirmed event source, fresh Alpaca underlying and option quotes, a common ATM call-put pair, valid timestamps, liquidity, and sufficient historical calibration. Submission requires an eligible decision, explicit review, a canonical approval, and an enabled process-level kill switch.”
>
> “If evidence is stale, the event is unconfirmed, or edge disappears after execution costs, the correct output is no trade. That restraint protects competition P&L from forced, low-quality activity.”

**If the live result abstains, say:**

> “This refusal is expected behavior. The agent has identified that the evidence is insufficient and preserved capital while recording the exact rejection reasons.”

**If showing an existing paper order, say:**

> “This receipt links the DecisionRecord, approval token, client-order ID, exact multi-leg plan, Alpaca broker-order ID, and reconciliation state. It is a complete decision-to-execution audit trail.”

---

## 5:25–6:25 — Evidence and honest performance measurement

**Screen:** `04 Evidence → Performance`

**Judging criteria:** P&L Performance, Presentation

**Narration:**

> “We separate three questions judges should ask. Does the system function correctly? Does each component improve decisions? And does it make money out of sample?”
>
> “The controlled ablation holds the LangGraph, contracts, sizing, random seed, fees, and accounting oracle constant. It compares the full agent with no trade, always-long volatility, always-short volatility, a disabled final governor, and a deterministic quant-only variant. This isolates the contribution of risk governance and agent context.”
>
> “We label this as synthetic functional evidence, not predictive alpha. The authoritative P&L claim is the realized Alpaca paper-account result shown in Command. Historical forecasts are scored separately against realized moves and interval coverage.”

**Point to:**

- Full-agent versus baseline P&L chart.
- B3 policy-breach count.
- Same-input ablation methodology.
- Historical forecast evaluation.
- Replay/synthetic disclosure.

**Key advantage:** CaiSheng makes its strongest evidence easy to understand while clearly disclosing what each result can and cannot prove.

---

## 6:25–7:00 — Closing statement

**Screen:** Return to `01 Command`.

**Narration:**

> “CaiSheng combines the four things required for a winning autonomous trading agent: an original volatility strategy, the official Alpaca agent ecosystem, non-bypassable risk and execution controls, and judge-readable proof.”
>
> “It does not merely recommend a trade. It discovers an opportunity, debates both sides, quantifies edge, sizes defined risk, submits through a guarded Alpaca paper gateway, reconciles the result, and explains when trading is not justified.”
>
> “That is CaiSheng: selective autonomy with a complete audit trail.”

---

## Thirty-second fallback version

> “CaiSheng is a LangGraph multi-agent options system for the $100,000 Alpaca paper competition. It predicts volatility mispricing rather than direction, while deterministic code controls pricing, sizing, and twenty risk gates. Our Lockbox visibly verifies Alpaca’s official CLI, read-only MCP V2, and four official agent skills; Alpaca’s APIs provide account state, option data, Level-3 paper orders, positions, and reconciliation. Only CaiSheng’s approval-bound gateway can mutate the account. Replay is isolated, and actual P&L comes only from Alpaca paper trading. CaiSheng trades only when executable edge survives costs and risk—otherwise it abstains.”

---

## Judge-question responses

### “Is the displayed P&L real?”

> “The Command screen shows Alpaca paper-account equity against the fixed $100,000 competition baseline. Evidence-page replay P&L is separately labelled synthetic and is not presented as live alpha.”

### “Is Lockbox an Alpaca product?”

> “No. Lockbox is our judge-facing proof method. Inside it are Alpaca’s real official technologies: the Alpaca CLI, Alpaca MCP Server V2, Alpaca agent skills, Trading API, and Market Data API.”

### “Why are there two MCP integrations?”

> “The official Alpaca MCP V2 proves native sponsor integration and is deliberately restricted to read-only asset and options-data toolsets. CaiSheng’s FastMCP gateway is the application’s policy-enforced interface; its only write operation requires canonical approval and routes through the same broker gateway as the UI and autonomous runner.”

### “Why use multiple agents?”

> “The agents have opposing mandates. One must justify long volatility, another must justify short volatility, and an independent critic can veto both. The disagreement is useful context, while deterministic code remains the final authority for money and risk.”

### “Can MCP bypass your risk system?”

> “No. The MCP write tool cannot construct an order from arbitrary legs. It accepts only a one-time canonical approval token and its matching persisted DecisionRecord ID, then calls the same broker gateway used by the lifecycle runner.”

### “What happens if Alpaca or market data fails?”

> “The system fails closed. Stale or unavailable account state, invalid quotes, missing contracts, or unknown order outcomes are surfaced and reconciled; they are never silently treated as valid.”

### “What is actually autonomous?”

> “The lifecycle can reconcile, monitor exact contracts, scan confirmed events, run the LangGraph, allocate candidates, create approved previews, submit when policy permits, manage exits, and produce daily reconciliation. Human approval and the submission kill switch are deployment policies, not missing strategy logic.”

### “What is your most original feature?”

> “The combination of dialectical volatility debate with deterministic executable-edge and portfolio governance. It uses AI for contextual disagreement, but preserves institutional trust boundaries around pricing, risk, and execution.”

### “Does passing the test suite prove alpha?”

> “No. Tests prove execution and safety behavior. Alpha must be demonstrated by locked forecasts and realized Alpaca paper results. We keep those claims separate.”

---

## Claims the presenter must not make

- “The replay P&L proves future alpha.”
- “MCP is connected” before the verification receipt returns `PASS`.
- “The system is live trading” when the submission kill switch is disabled.
- “The model predicts direction.”
- “Every eligible event produces a trade.”
- “Tests prove profitability.”
- “An order filled” unless an Alpaca broker receipt and reconciliation state support it.
