# ⚡ VolAgent Alpha

> **Multi-Agent Options Volatility & Event Desk (Alpaca Hackathon Prototype)**  
> *Target Track: Track 02 — Volatility & Event Trading Agents*

---

## 🎯 1. One-Sentence Pitch

**VolAgent Alpha** is a neuro-symbolic multi-agent options volatility desk that forecasts whether an equity will move more or less than its options market has priced around after-market-close (AMC) earnings announcements, evaluates opposing volatility theses via dialectical agent debate, enforces a 20-point deterministic quant risk gate, and executes defined-risk delta-neutral paper trades (`LONG_STRADDLE`, `SHORT_IRON_BUTTERFLY`, or `NO_TRADE`) through Alpaca.

---

## 🏆 2. Strict Track Fit: Movement & Implied Volatility (Never Price Direction)

In strict compliance with **Track 02 (Volatility & Event Trading Agents)**:
* **Non-Directional Target:** The system forecasts unsigned absolute move magnitude ($Y_e = |\ln(S_{\text{exit}}/S_{\text{entry}})|$) and post-event Implied Volatility change ($\Delta IV_e$), never price direction ($S \uparrow$ or $S \downarrow$).
* **Delta-Neutral Structures:** Permitted strategies are strictly limited to delta-neutral ATM Long Straddles, defined-risk Short Iron Butterflies with protective wings, or `NO_TRADE`. No standalone directional options.
* **Dialectical Volatility Debate:** Opposing specialized agents debate whether the market is underpricing jump variance (Long Vol) or overpricing the Variance Risk Premium / IV crush (Short Vol).

---

## 🧠 3. Neuro-Symbolic Quant Architecture

```
                               ┌────────────────────────────────────────────────────────┐
                               │                 Alpaca Pro Terminal                    │
                               │        (Interactive Payoff, Greeks, Dynamic Audit)     │
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
│                                 │  - Historical Shrinkage Baseline  │                                                 │
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
│   - Hard max risk budget <= 1.0% NAV | Dollar Delta |(net_delta * S)| / NAV <= 2.0% | Worst Stress Loss <= 1.0% NAV   │
│   - Topological wing verification for Iron Butterfly (Kp,long < Kp,short = Kc,short < Kc,long)                       │
└───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┘
                                                    │ (Approved Order Payload)
                                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       SAFE EXECUTION & SQLITE LEDGER                                                  │
│   - Transactional SQLite ledger with atomic compare-and-set approval tokens (PREVIEWED -> APPROVED -> SUBMITTING)   │
│   - Explicit SimulatedPaperBroker vs AlpacaPaperBroker Level-3 MLEG order dispatch                                    │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ 4. Five-Minute Quickstart (Zero Keys Required)

VolAgent Alpha contains **three synthetic archetype scenarios** (`NVDA`, `TSLA`, and `AAPL`) that run instantly with **zero API keys required**:

```bash
# 1. Clone repository
git clone https://github.com/your-username/volagent-alpha
cd volagent-alpha

# 2. Install dependencies
uv pip install -r requirements.txt

# 3. Launch the Streamlit Judge Dashboard
streamlit run app.py
```

### Or run directly from terminal CLI:
```bash
# Test NVDA (Long Straddle scenario)
python cli.py --symbol NVDA

# Test TSLA (Short Iron Butterfly scenario)
python cli.py --symbol TSLA

# Test AAPL (Stale Quote Risk Rejection scenario)
python cli.py --symbol AAPL
```

---

## 📐 5. Mathematical Methodology & Risk Invariants

1. **Executable Ask/Bid Edge Formulation:**
   $$\text{Long Edge} = \text{Forecast Median} - M_{\text{ask}}, \quad \text{Short Edge} = M_{\text{bid}} - \text{Forecast Median}$$
   $$\text{where } M_{\text{ask}} = \frac{\text{Call}_{\text{ask}} + \text{Put}_{\text{ask}}}{S}, \quad M_{\text{bid}} = \frac{\text{Call}_{\text{bid}} + \text{Put}_{\text{bid}}}{S}$$
2. **Positive Loss Expected Shortfall ($\text{ES}_{95}$):**
   $$\text{Loss} = \max(-\text{PnL}, 0), \quad \text{VaR}_{95} = \text{Quantile}(\text{Loss}, 0.95), \quad \text{ES}_{95} = \mathbb{E}[\text{Loss} \mid \text{Loss} \ge \text{VaR}_{95}]$$
3. **True Dollar Delta Neutrality:**
   $$\text{Dollar Delta NAV Ratio} = \frac{|\text{Net Share Delta} \times S|}{\text{NAV}} \le 2.0\%$$
4. **Stress Loss Hard Cap:**
   $$\frac{\text{Worst 2D Stress Loss}}{\text{NAV}} \le 1.0\%$$

---

## 🛡️ 6. Safety & Paper-Trading Constraints

* **Paper Trading Only:** The application strictly enforces paper endpoints and rejects live trading endpoints.
* **Submission Kill-Switch:** `VOLAGENT_ALLOW_ORDER_SUBMISSION` defaults to `False`. Real broker submission requires explicit opt-in.
* **Idempotency & One-Time Approval:** SQLite transactional ledger enforces that an approved token is consumed atomically and dispatched at most once.

---

## 📚 7. Research Foundations & Attribution

* **TradingAgents Dialectical Framework:** Architecturally inspired by [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (*Xiao et al., arXiv:2412.20138*), adapted from directional stock picking into options distributions and event volatility.
* **Variance Risk Premium (VRP):** Bollerslev, Tauchen, Zhou (2009); Carr & Wu (2009).
* **Post-Earnings Announcement IV Dynamics:** Patel et al. (2020).

---

## ⚖️ 8. Disclaimer

*VolAgent Alpha is an educational and research prototype built for the Alpaca AI Trading Agents Hackathon. It trades exclusively in simulated/paper trading environments and does not constitute financial or investment advice.*
