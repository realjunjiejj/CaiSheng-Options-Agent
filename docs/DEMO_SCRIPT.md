# 🎬 VolAgent Alpha: 90-Second Winning Demo Script

> **Target Track:** Track 02 — Volatility & Event Trading Agents  
> **Format:** 90-Second Video or Live Judge Walkthrough

---

## ⏱️ Video Breakdown & Screen Sequence

### 0:00 – 0:15 | Track Fit & Non-Directional Stance
* **Screen:** Streamlit Pro Terminal (`app.py`), Ticker `NVDA` selected.
* **Voiceover / Script:**
  > *"Welcome to VolAgent Alpha. For Track 2, we built a neuro-symbolic multi-agent options volatility desk. Unlike generic bots that try to predict if a stock is going up or down, VolAgent Alpha forecasts unsigned absolute move magnitude $|r|$ and post-earnings IV crush around scheduled AMC earnings."*
* **Visual Cue:** Point to **"Forecast Absolute Move: 8.2%"** vs **"ATM Straddle Implied Move: 6.1%"** with **"Directional Bias: NONE"**.

---

### 0:15 – 0:35 | Dialectical Multi-Agent Debate
* **Screen:** Expand **"Agent Debate & Thesis Analysis"** card.
* **Voiceover / Script:**
  > *"Our pipeline deploys opposing specialized LLMs grounded in frozen point-in-time SEC disclosures. The Long-Vol Advocate argues that guidance ambiguity justifies paying straddle debit. The Short-Vol Advocate argues that historical IV crush will destroy vega. The Model-Risk Critic independently verifies all citation IDs and checks for temporal lookahead leakage."*
* **Visual Cue:** Show Long Vol thesis vs Short Vol thesis and verified `EVID-NVDA-10Q-01` citation tags.

---

### 0:35 – 0:55 | Mathematical Pricing & Payoff Proof
* **Screen:** Interactive Payoff Plot & Greeks Attribution.
* **Voiceover / Script:**
  > *"On the quant layer, we compute exact signed cash-flow payoffs and coherent Expected Shortfall (ES95). For NVDA, we select an ATM Long Straddle with positive EV after bid-ask slippage. In Tab 4, our Rough Volatility engine simulates Lifted Heston dynamics with Hurst parameter H=0.10, capturing the power-law skew blowup at front maturities."*
* **Visual Cue:** Hover over the dynamic payoff plot and switch briefly to the **"🌪️ Rough Volatility Simulator"** tab showing the implied volatility smile comparison.

---

### 0:55 – 1:15 | 20-Point Deterministic Risk Gate & Paper Execution
* **Screen:** **"20-Point Deterministic Risk Gate"** & **"Alpaca Paper Order Preview"**.
* **Voiceover / Script:**
  > *"Before any order can execute, it must pass our deterministic 20-point risk gate. Derived agent fields are never trusted—the gate independently recomputes maximum loss, stress limits, and enforces true spot-scaled dollar delta under 2% NAV. Once human-authorized, an atomic CAS lock submits a Level-3 MLEG paper limit order to Alpaca."*
* **Visual Cue:** Show 20 green risk checks (`Worst Stress Loss <= 1.0% NAV`, `Dollar Delta <= 2.0% NAV`) and the SHA-256 fingerprint on the JSON execution receipt.

---

### 1:15 – 1:30 | Replay Scoreboard & Restraint Proof
* **Screen:** Tab 2: **"📊 Replay Benchmarks"** and switch to `AAPL`.
* **Voiceover / Script:**
  > *"Finally, on AAPL where market data had stale quotes, our agent demonstrated 100% restraint discipline, rejecting the trade with a NO_TRADE veto where naive bots lost thousands. Across our replay benchmarks, VolAgent Alpha delivered +$461.50 in net P&L with zero unhandled risk violations. Thank you."*
* **Visual Cue:** Show AAPL `NO_TRADE` fail-closed receipt and the benchmark summary table.
