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

## 🌪️ 5. Frontier Quantitative Engine: Rough Volatility & Markovian Lifting

VolAgent Alpha moves beyond standard Black-Scholes and Markovian Heston diffusions to model the empirical reality of short-dated pre-earnings options:
* **Rough Volatility ($H \approx 0.10$):** High-frequency log-volatility behaves as fractional Brownian motion (Gatheral, Jaisson, & Rosenbaum 2018), generating the explosive short-term implied volatility skew power-law blowup $\sim T^{H-1/2} \approx T^{-0.40}$.
* **Markovian Lifting (Abi Jaber, Larsson, & Pulido 2019):** Lifts the singular fractional kernel $K(t) = \frac{t^{H-1/2}}{\Gamma(H+1/2)}$ into an $n$-dimensional Markovian system of Ornstein-Uhlenbeck (OU) factors with geometric mean-reversion speeds, restoring fast $O(N)$ Monte Carlo simulation.
* **Truncated Path Signatures (Lyons 1998):** Level-2 iterated path integrals $\mathbb{S}(X)^{\le 2}$ capturing non-linear geometric shape, lead-lag relationships, and the Levy area of volatility trajectories.

---

## 📐 6. Mathematical Methodology & Risk Invariants

1. **Exact Signed Cash Flow Payoffs:**
   $$\text{PnL}(S) = \text{Position Value}(S) - \text{Entry Cash Flow} - \text{Transaction Friction}$$
   - Long Straddle Center ($S=K$): $0 - \text{Debit} = -\text{Debit}$.
   - Short Iron Butterfly Center ($S=K$): $0 - (-\text{Credit}) = +\text{Credit}$.
2. **Asymmetric Wing Max Loss Formula:**
   $$\text{Max Loss} = \max(K_{p,\text{short}} - K_{p,\text{long}}, K_{c,\text{long}} - K_{c,\text{short}}) \times 100 \times \text{Qty} - (\text{Net Credit} \times 100 \times \text{Qty})$$
3. **Positive Loss Expected Shortfall ($\text{ES}_{95}$ / CVaR):**
   $$\text{Loss} = \max(-\text{PnL}, 0), \quad \text{VaR}_{95} = \text{Quantile}(\text{Loss}, 0.95), \quad \text{ES}_{95} = \mathbb{E}[\text{Loss} \mid \text{Loss} \ge \text{VaR}_{95}]$$
4. **True Dollar Delta Neutrality:**
   $$\text{Dollar Delta NAV Ratio} = \frac{|\text{Net Share Delta} \times S|}{\text{NAV}} \le 2.0\%$$
5. **Stress Loss Hard Cap:**
   $$\frac{\text{Worst 2D Stress Loss}}{\text{NAV}} \le 1.0\%$$

---

## 🧪 7. 69-Item Automated Test Suite (100% Pass Rate)

VolAgent Alpha maintains an adversarial automated test suite covering:
* **Quant Pricing & Greeks:** Black-Scholes parity, analytical Greeks, Brent root-finding, Brenner-Subrahmanyam IV inversion.
* **Rough Volatility & Lifting:** Fractional kernel approximation weights, Lifted Heston simulation shapes, path signature tensor dimensions.
* **Risk Gates & Topologies:** Independent raw quote recomputation, 20-point risk checklist, dollar delta scaling, asymmetric butterfly wing caps.
* **Execution Safety:** SQLite transactional ledger idempotency, 50-thread concurrent CAS locking, pre-dispatch SHA-256 fingerprint verification.
* **Agent & Temporal Integrity:** Citation ID validation, temporal leakage scans ($t_{\text{obs}} \le t_{\text{decision}}$), directional bias filters.
* **Headless UI Rendering:** Streamlit `AppTest` lifecycle verification across all 4 top-level tabs.

```bash
# Run the complete test suite
pytest -v tests/
# Output: 69 passed in 7.13s (100% pass rate)
```

---

## 🛡️ 8. Safety & Paper-Trading Constraints

* **Paper Trading Only:** The application strictly enforces paper endpoints and rejects live trading endpoints.
* **Submission Kill-Switch:** `VOLAGENT_ALLOW_ORDER_SUBMISSION` defaults to `False`. Real broker submission requires explicit opt-in.
* **Idempotency & One-Time Approval:** SQLite transactional ledger enforces that an approved token is consumed atomically and dispatched at most once.
* **Level-3 MLEG Order Serialization:** Formats multi-leg limit orders with explicit per-leg `position_intent` (`buy_to_open` / `sell_to_open`).

---

## 📚 9. Research Foundations & Academic Whitepaper

For the complete theoretical foundations, financial economics proofs, and LaTeX formulations, refer to:
* **Whitepaper:** [`docs/ACADEMIC_FOUNDATIONS.md`](file:///Users/yanjunjie/Documents/Alpaca/docs/ACADEMIC_FOUNDATIONS.md)
* **Bibliography Registry:** [`src/volagent/research/bibliography.py`](file:///Users/yanjunjie/Documents/Alpaca/src/volagent/research/bibliography.py)
* **Third-Party Open-Source Attribution:** [`THIRD_PARTY_SOURCES.md`](file:///Users/yanjunjie/Documents/Alpaca/THIRD_PARTY_SOURCES.md)

---

## ⚖️ 10. Disclaimer

*VolAgent Alpha is an educational and research prototype built for the Alpaca AI Trading Agents Hackathon. It trades exclusively in simulated/paper trading environments and does not constitute financial or investment advice.*
