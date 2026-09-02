# ⚡ CaiSheng · Auditable Multi-Agent Options Alpha

> **Autonomous multi-agent options volatility trading desk built for the Alpaca Options Alpha Hackathon (Track 02).**  
> Trades movement only when the quantified edge survives adversarial multi-agent debate, governed by a 20-point deterministic risk engine.

🌐 **Live Demo:** [https://caisheng-ui-34syptghka-uc.a.run.app](https://caisheng-ui-34syptghka-uc.a.run.app)

---

## ⚡ Quickstart (Test the App — Zero API Keys Required)

CaiSheng includes frozen point-in-time replay scenarios that run out of the box with zero external credentials.

### 1. Install Dependencies
```bash
git clone https://github.com/realjunjiejj/CaiSheng-Options-Agent.git
cd CaiSheng-Options-Agent
uv sync --locked
```

### 2. Launch the Web UI
```bash
uv run streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) to explore the continuous canvas desk.

### 3. Run Scenarios via CLI
```bash
uv run python cli.py --symbol NVDA
uv run python cli.py --symbol TSLA
uv run python cli.py --symbol AAPL
```

### 4. Run Automated Test Suite
```bash
uv run pytest -q
```

---

## 🧠 System Architecture

```
                               ┌────────────────────────────────────────────────────────┐
                               │             Continuous Canvas Cockpit                  │
                               │        (Interactive Greeks, Payoff Curves, Audit)      │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
                                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                             LANGGRAPH MULTI-AGENT PIPELINE                                            │
│                                                                                                                       │
│   ┌────────────────────────────────┐                             ┌────────────────────────────────┐                   │
│   │     EventMagnitudeAgent        │                             │      VolatilityQuantEngine     │                   │
│   │  - Point-in-time filing audit  │                             │  - Black-Scholes & Greeks math │                   │
│   │  - Guidance uncertainty score  │                             │  - Realized vs Implied Vol     │                   │
│   │  - Analyst dispersion index    │                             │  - Surface & Expiry Selection  │                   │
│   └───────────────┬────────────────┘                             └────────────────┬───────────────┘                   │
│                   │                                                               │                                   │
│                   └───────────────────────────────┬───────────────────────────────┘                                   │
│                                                   ▼                                                                   │
│                                 ┌───────────────────────────────────┐                                                 │
│                                 │     Deterministic Forecast        │                                                 │
│                                 │  - Empirical Bayes Shrinkage      │                                                 │
│                                 │  - Post-Event IV Crush Model      │                                                 │
│                                 └─────────────────┬─────────────────┘                                                 │
│                                                   ▼                                                                   │
│                                 ┌───────────────────────────────────┐                                                 │
│                                 │   Dialectical Volatility Debate   │                                                 │
│                                 │  - Long Vol Advocate (Jump Edge)  │                                                 │
│                                 │  - Short Vol Advocate (VRP / IV)  │                                                 │
│                                 └─────────────────┬─────────────────┘                                                 │
│                                                   ▼                                                                   │
│                                 ┌───────────────────────────────────┐                                                 │
│                                 │      Model-Risk Critic Agent      │                                                 │
│                                 │  - Stale quote & leakage audit    │                                                 │
│                                 │  - First-class NO_TRADE authority │                                                 │
│                                 └─────────────────┬─────────────────┘                                                 │
└───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       20-POINT DETERMINISTIC RISK GATE                                                │
│   - Hard max risk budget ≤ 0.5% NAV ($500) | Dollar Delta |(net_delta * S)| / NAV ≤ 2.0%                              │
│   - Sector concentration ceiling ≤ 25% | Max 1 entry / day | Topological wing verification (Kp,l < Kp,s = Kc,s < Kc,l)│
└───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       SAFE EXECUTION & SQLITE LEDGER                                                  │
│   - Transactional SQLite ledger with atomic compare-and-set approval tokens (PREVIEWED -> APPROVED -> SUBMITTING)   │
│   - Alpaca FastMCP Gateway & Trading API Level-3 Multi-Leg (MLEG) order execution                                     │
│   - Automated two-way broker position reconciliation and SHA-256 intent verification                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Alpaca Technology Integration

- **Trading API (Level-3 MLEG):** Native multi-leg order execution (`OrderClass.MLEG`) with deterministic fill reconciliation.
- **FastMCP Server V2:** Model Context Protocol tool server (`src/volagent/data/alpaca_mcp.py`) exposing audited account, position, and clock tools with fail-closed safety.
- **CLI Tooling:** Automated preflight (`python cli.py --preflight`) and reconciliation receipts (`python cli.py --reconcile`).

---

## 📁 Repository Structure

```
├── app.py
├── cli.py
├── config/
├── src/volagent/
│   ├── agents/
│   ├── data/
│   ├── domain/
│   ├── execution/
│   ├── quant/
│   └── ui/
├── data/
│   ├── replay/
│   └── evaluation/
├── deploy/
├── docs/
└── tests/
```
