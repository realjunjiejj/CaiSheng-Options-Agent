# Routes & Page Mapping

The application is structured into 7 primary operational tabs:

## 1. `/cockpit` — 🏛️ Capital Command & Autonomous Cockpit
- **Component File**: `src/volagent/ui/pages/cockpit.py`
- **Summary**: Real-time authenticated Alpaca paper account state ($100k competition starting NAV, current equity, buying power, daily P&L), persistent circuit breaker monitoring ($1,500 daily loss halt, 5.0% HWM drawdown halt), risk budget utilization (2.0% / $2,000 NAV cap), CLI operational receipts, and immutable DecisionRecord timeline.

## 2. `/desk` — ⚡ Pro Trading Desk
- **Component File**: `app.py` (Pro Desk Tab)
- **Summary**: Interactive live multi-agent dialectic debate, archetype switcher (NVDA Long Vol, TSLA Short Vol, AAPL Stale Data Veto), Long-Vol vs Short-Vol debate split, Model-Risk Critic audit, 20-Point Quantitative Risk Gate, Plotly payoff diagram, and gated 3-step execution portal.

## 3. `/canary` — 🧪 Live Paper Canary
- **Component File**: `src/volagent/ui/pages/live_canary.py`
- **Summary**: Direct inspection of live Alpaca option chains, market clock state, FastMCP SSE endpoint status, and 1-contract canary submission tool.

## 4. `/historical` — ⏪ Historical Forecast Replay
- **Component File**: `src/volagent/ui/pages/historical_replay.py`
- **Summary**: Multi-quarter out-of-sample historical earnings event evaluations comparing implied move vs model forecast vs realized stock jump.

## 5. `/benchmarks` — 📊 Replay Benchmarks & Controlled Ablation
- **Component File**: `src/volagent/ui/pages/scoreboard.py`
- **Summary**: The "30-Second Result" bar chart comparing Full Model vs B3 Ungated Agent vs B4 Quant Only vs Naive Baselines, isolation highlight cards, and canonical JSON receipt download.

## 6. `/research` — 📚 Academic Foundations
- **Component File**: `src/volagent/ui/pages/research.py`
- **Summary**: Peer-reviewed literature registry (Carr-Wu VRP, Patell-Wolfson IV Crush, Rockafellar-Uryasev CVaR, Brenner-Subrahmanyam, Gatheral Rough Vol).

## 7. `/rough_vol` — 🌪️ Rough Volatility Simulator
- **Component File**: `src/volagent/ui/pages/rough_vol_simulator.py`
- **Summary**: Interactive quantitative research sandbox with Hurst parameter $H \in [0.05, 0.50]$ sliders and volatility smile comparison curves.
