# CaiSheng — 90-Second Judge Demo

> Track: Options Alpha Agents
> Rule: never claim replay P&L as live performance; show the current Alpaca paper-account result from the UI.

## 0:00–0:15 — Mandate and live proof

**Screen:** `01 Command`

**Say:**

> “CaiSheng is an autonomous options-alpha agent operating under the competition’s $100,000 Alpaca paper mandate. This screen is not a mock: current equity comes from Alpaca, and every integration claim is verified or fails closed.”

**Do:** Point to Current Equity and Circuit Breaker Status, then the competition strip immediately below it: `AUTONOMY ARMED/DISARMED`, `PAPER ONLY`, $250 target/$500 hard risk, one entry per day, two open positions, `SPY/QQQ/IWM`, and lease expiry. Explain that `python cli.py --competition-arm` issues an account/config-bound eight-hour receipt but does not place an order, while `python cli.py --competition-disarm` immediately blocks new entries without interrupting position monitoring. The scheduler never re-arms itself. Run **Verify Official Alpaca Lockbox**, **Run CaiSheng Preflight**, and **Verify Guarded MCP**. No receipt exposes the account ID or credentials.

## 0:15–0:40 — Agent logic and mathematical decision

**Screen:** `02 Agent`

**Say:**

> “The LangGraph workflow pits a long-volatility advocate against a short-volatility advocate, then sends both to an independent model-risk critic. The option market is the forecast anchor. Deterministic code—not an LLM—owns any residual correction, confidence-bound edge, Monte Carlo expected value, structure selection, sizing, and the twenty-point risk gate.”

**Do:** Acknowledge the **SEALED REPLAY** label. Select one archetype, show implied move versus forecast move, opposing theses, exact option legs, payoff curve, and the dynamically derived gate result. Emphasize that this page can execute only in the local simulator.

## 0:40–1:05 — Fresh Alpaca path and safety

**Screen:** `03 Paper Trade`

**Say:**

> “Fresh Alpaca paper trading is isolated from replay. The canary requires a confirmed event, current underlying and option quotes, a common ATM call-put pair, valid timestamps, liquidity, calibrated history, and portfolio capacity. It can abstain; that is a valid autonomous decision.”

**Do:** Show the kill-switch state. If submission is disabled, run **live canary — no order**. If a fully approved competition trade already exists, show its canonical DecisionRecord, one-time approval, order receipt, and reconciliation—do not create an improvised trade for the demo.

## 1:05–1:25 — Evidence without overclaiming

**Screen:** `04 Evidence`

**Say:**

> “This controlled ablation uses the same LangGraph, contracts, sizing, seed, and accounting oracle across variants. It demonstrates what the governor and agent context contribute, but it is explicitly synthetic functional evidence—not proof of predictive alpha.”

**Do:** Show the ablation P&L chart, B3 policy-breach evidence, and the historical forecast view. Then state the actual competition-account realized P&L shown in Command.

## 1:25–1:30 — Close

**Say:**

> “CaiSheng’s edge is selective autonomy: quantify volatility mispricing, debate both sides, trade only defined risk, and leave an auditable Alpaca receipt for every decision.”

## Demo guardrails

- Do not call historical replay “live,” “out-of-sample alpha,” or “executable Alpaca P&L.”
- Do not say official MCP is connected until the Lockbox returns `PASS`; do not say the guarded MCP is connected until its separate verification passes.
- Do not expose account IDs, API keys, secrets, or raw MCP responses on screen.
- Do not submit a paper order merely to create excitement; show an existing eligible trade or a fail-closed abstention.
- If market data or the event source is unavailable, use the sealed replay and explain why the live path refused to proceed.
