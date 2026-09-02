# ⚡ CaiSheng (财神) · Auditable Multi-Agent Options Alpha

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Tests Passing](https://img.shields.io/badge/tests-349%20passed-emerald.svg)](tests/)
[![Google Cloud Run](https://img.shields.io/badge/Cloud%20Run-Live%20Demo-4285F4.svg)](https://caisheng-ui-34syptghka-uc.a.run.app)
[![Alpaca Trading](https://img.shields.io/badge/Alpaca-Level--3%20MLEG-FACC15.svg)](https://alpaca.markets/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-slate.svg)](NOTICE.md)

> **Autonomous multi-agent options volatility trading desk built for the Alpaca Options Alpha Hackathon (Track 02).**
> Trades movement only when the quantified edge survives adversarial multi-agent debate, governed by a 20-point deterministic risk engine.

🌐 **Live Judge Demo:** [https://caisheng-ui-34syptghka-uc.a.run.app](https://caisheng-ui-34syptghka-uc.a.run.app)  
🎥 **90-Second Pitch Video:** [`submission/CaiSheng_Judge_Pitch_90s.mp4`](submission/CaiSheng_Judge_Pitch_90s.mp4)  
📊 **Presentation Deck:** [`submission/CaiSheng_Judge_Deck.pptx`](submission/CaiSheng_Judge_Deck.pptx)  
📄 **One-Page Whitepaper:** [`docs/ONE_PAGE_WRITEUP.md`](docs/ONE_PAGE_WRITEUP.md)

---

## 🎯 1. Executive Summary & Core Alpha

CaiSheng scans confirmed corporate earnings and liquid index volatility (`SPY`, `QQQ`, `IWM`, `NVDA`, `TSLA`, `AAPL`) in a **$100,000 Alpaca paper mandate**.

The alpha thesis is **strictly non-directional**: options often misprice event-driven jump variance and post-announcement volatility crush. CaiSheng forecasts unsigned move magnitude ($Y_e = |\ln(S_{\text{exit}}/S_{\text{entry}})|$) and post-event IV changes ($\Delta IV_e$), never price direction.

### Neuro-Symbolic Principle
* **LLMs Reason & Challenge:** Specialized LangGraph agents formulate competing hypotheses (Long Volatility vs. Short Volatility) and challenge assumptions through an independent Model-Risk Critic.
* **Deterministic Code Decides & Executes:** Pricing (Black-Scholes / Bivergent), expected value calculation, contract selection, sizing, the 20-point risk gate, and order dispatch are strictly owned by deterministic mathematical algorithms—not LLMs.
* **Defined-Risk Mandate:** Only three actions are permitted:
  1. `LONG_STRADDLE` (Delta-neutral ATM call + put to capture underpriced jump variance)
  2. `SHORT_IRON_BUTTERFLY` (Defined-risk wings to capture overpriced IV crush / Variance Risk Premium)
  3. `NO_TRADE` (Disciplined capital preservation when edge is insufficient or risk limits are reached)

---

## 🧠 2. System Architecture & Decision Pipeline

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
                                                    │ (Approved Order Token)
                                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       SAFE EXECUTION & SQLITE LEDGER                                                  │
│   - Transactional SQLite ledger with atomic compare-and-set approval tokens (PREVIEWED -> APPROVED -> SUBMITTING)   │
│   - Alpaca FastMCP Gateway & Trading API Level-3 Multi-Leg (MLEG) order execution                                     │
│   - Automated two-way broker position reconciliation and SHA-256 intent verification                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 3. Alpaca Technology Lockbox

CaiSheng deeply integrates with Alpaca's modern developer infrastructure:

1. **Alpaca Trading API (Level-3 MLEG):**
   * Native multi-leg order dispatch (`OrderClass.MLEG`) executing simultaneous multi-strike options structures with deterministic fill reconciliation.
   * Real-time market clock, quote streaming, and account equity synchronization.
2. **Alpaca FastMCP Server V2:**
   * Standalone Model Context Protocol service (`src/volagent/data/alpaca_mcp.py`) exposing read and execution tools.
   * All tool calls are sanitized and persisted to SQLite audit trails with API secrets redacted.
   * Execution tools fail closed unless pre-approved by the 20-point risk governor.
3. **Alpaca CLI Preflight & Reconciliation:**
   * Automated CLI preflight (`python cli.py --preflight`) verifying account health and starting equity.
   * Daily reconciliation reporter (`python cli.py --reconcile`) generating cryptographic audit receipts.

---

## ⚡ 4. 60-Second Quickstart (Zero API Keys Required)

CaiSheng includes frozen point-in-time replay scenarios that run out of the box with **zero external API keys**:

### 1. Install Environment
```bash
# Clone the repository
git clone https://github.com/realjunjiejj/CaiSheng-Options-Agent.git
cd CaiSheng-Options-Agent

# Install locked dependencies via uv
uv sync --locked
```

### 2. Launch Continuous Canvas Studio
```bash
uv run streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser to inspect the interactive live dashboard.

### 3. Run Command Line Scenarios
```bash
# Run Long Straddle scenario (NVDA)
uv run python cli.py --symbol NVDA

# Run Short Iron Butterfly scenario (TSLA)
uv run python cli.py --symbol TSLA

# Run Risk-Gate Rejection scenario (AAPL)
uv run python cli.py --symbol AAPL
```

### 4. Run Automated Test Suite
```bash
uv run pytest -q
# All 349 tests pass in ~24s
```

---

## 📊 5. Empirical Performance & Verification

Tested across historical volatility events and out-of-sample earnings releases:

| Metric | CaiSheng (Multi-Agent + Risk Gate) | Baseline (Single-LLM Trader) |
| :--- | :--- | :--- |
| **Cumulative Replay P&L** | **+$2,044.00** | -$1,420.00 |
| **Max Drawdown** | **0.38%** | 4.12% |
| **Risk Gate Violations** | **0 (100% Compliant)** | 7 breaches |
| **Abstention Discipline** | **33.3% (Selective)** | 0% (Over-traded) |
| **Ledger Idempotency** | **100% (0 Orphans)** | Unverified |

---

## 📁 6. Repository Map

```
├── app.py                      # Continuous canvas Streamlit cockpit
├── cli.py                      # Operator CLI (preflight, scan, reconcile)
├── config/                     # Competition & demo configuration YAMLs
├── src/volagent/
│   ├── agents/                 # LangGraph agents (Long Vol, Short Vol, Critic)
│   ├── data/                   # Alpaca Trading API SDK & FastMCP service
│   ├── domain/                 # Strongly typed Pydantic domain models
│   ├── execution/              # MLEG order mapper, SQLite ledger, runtime lock
│   ├── quant/                  # Black-Scholes pricing, rough vol, 20 risk gates
│   └── ui/                     # Emil Kowalski continuous canvas theme & charts
├── data/
│   ├── replay/                 # Frozen point-in-time market scenarios
│   └── evaluation/             # Out-of-sample benchmark datasets & receipts
├── deploy/                     # Google Cloud Run deployment scripts & systemd
├── docs/                       # Official submission writeup, lockbox, and specs
├── submission/                 # Cover image, 90s pitch video, presentation deck
└── tests/                      # 349 unit & adversarial tests (100% green)
```

---

## ⚖️ 7. License & Compliance

Licensed under the MIT License. Designed strictly for paper trading and research evaluation in the Alpaca Options Alpha Hackathon. See [`NOTICE.md`](NOTICE.md) for third-party citations and disclosures.
