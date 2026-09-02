# 🎨 UI/UX Design Brief & Figma Prompt: CaiSheng (Options Alpha)

## 📌 Project Overview
We are building a **modern, institutional-grade web trading terminal and executive dashboard** for **CaiSheng (Options Alpha)**, an autonomous multi-agent options volatility and event trading desk built natively on **Alpaca's Level-3 Options API**.

The design language must directly adopt the **official Alpaca visual identity (`alpaca.markets`)** combined with the sleek, high-contrast aesthetic of top-tier developer and quant platforms (e.g., Linear, TradingView Pro, Vercel, Stripe).

---

## 🎨 Visual Identity & Design System

### 1. Color Palette (Alpaca Pro Theme)
* **Signature Brand Yellow:** `#FFD000` (Alpaca Yellow — used for hero moments, active tabs, primary CTAs, and key accents).
* **Vibrant Hover Yellow:** `#FFE033`
* **Obsidian Background Canvas:** `#0C0F14` (Deep obsidian) / `#141820` (Card container surfaces).
* **Borders & Dividers:** `#252C38` (Razor-sharp 1px subtle borders) / `#30363D`.
* **Typography Colors:** `#FFFFFF` (Headlines & metrics), `#9DA7B3` (Secondary text), `#6B7785` (Muted labels).
* **Financial Indicators:**
  * **Emerald Profit / Long Vol:** `#00C805` (Alpaca Emerald Green / Realized Gains / Gate Pass)
  * **Coral Loss / Warning:** `#FF3B30` (Alpaca Coral Red / Realized Loss / Gate Veto)
  * **Electric Cyan:** `#0070F3` (Market Forecasts / Tech Badges)
  * **Volatility Lilac:** `#9333EA` / `#C084FC` (IV Crush / Short Butterfly)

### 2. Typography & Hierarchy
* **Headings & Navigation:** `Inter` or `Aeonik` (Font weights: 700, 800, 900) with tight letter-spacing (`-0.03em`).
* **Financial Tickers, Greeks, Prices & Code:** `JetBrains Mono` or `Fira Code` (Font weights: 600, 700).

### 3. Visual Components & Styling Rules
* **Cards & Containers:** `16px` border-radius, `1px solid #252C38`, subtle drop shadow (`0 8px 24px rgba(0,0,0,0.35)`), hover border glow (`rgba(255, 208, 0, 0.4)`).
* **Buttons:** Solid Alpaca Yellow (`#FFD000`) with Black text (`#000000`), `10px` radius, bold font. Secondary buttons: Dark `#1C222E` with white text.
* **Code Preview Boxes:** Dark `#080B10` background with macOS window control dots (🔴 🟡 🟢), line numbers, and Python syntax highlighting.

---

## 🖥️ Platform Navigation & Information Architecture

The platform features a persistent **Alpaca Yellow Hero Banner** at the top, followed by **7 core views**:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🦙 Alpaca / CaiSheng Options Alpha Hero Banner with Status Pills & $100,000 Mandate                     │
├──────────────┬──────────────┬───────────────┬───────────────────┬──────────────┬───────────┬───────────┤
│ 🏛️ Capital   │ ⚡ Pro        │ 🧪 Live Paper │ ⏪ Historical     │ 📊 Replay    │ 📚 Papers │ 🌪️ Rough  │
│    Command   │   Desk       │    Canary     │    Forecasts      │   Benchmarks │   Library │   Vol Sim │
└──────────────┴──────────────┴───────────────┴───────────────────┴──────────────┴───────────┴───────────┘
```

---

## 📐 Screen-by-Screen Specifications (Every Feature Must Be Shown)

### 1. Header & Persistent Hero Banner
* **Top Navigation Bar:**
  * Alpaca logo mark 🦙 + **Alpaca / CaiSheng Options Alpha**.
  * **Live Status Pills:**
    * `PAPER TRADING: $100,000.00`
    * `LEVEL-3 MLEG API: ACTIVE`
    * `FASTMCP SERVER: READY`
    * `GATEWAY STATUS: CLEAN (0 HALTS)`
* **Hero Headline & Subtitle:**
  * Bold Headline: **"API for Stock, Options, Crypto Trading & more"**
  * Subtitle: *"Autonomous multi-agent volatility trading system built natively on Alpaca's Level-3 Options API. Harnessing dialectical AI debate, rough volatility modeling, and non-bypassable risk gates."*
  * CTA Badge: `⚡ $100,000 Competition Portfolio Mandate Active`

---

### 2. Screen 1: 🏛️ Capital Command & Autonomous Cockpit
* **Executive KPI Cards (4 Grid):**
  1. *Starting Competition NAV:* `$100,000.00` (Fixed Mandate)
  2. *Current Equity & P&L:* `$100,000.00` (with green/red total P&L delta)
  3. *Reserved Risk vs Cap:* `$0.00 / $2,000.00` (2.0% NAV risk limit with visual capacity progress bar)
  4. *Circuit Breakers:* `$1,500 Daily Loss Halt` & `5.0% Drawdown Halt` (Status: `CLEAN / OPERATIONAL`)
* **Audit Receipt Actions:** 3 quick-action buttons:
  * `[ Run CLI Preflight Verification ]`
  * `[ Run Daily Reconciliation ]`
  * `[ View MCP Audit Log ]`
* **Two-Column Split Section:**
  * *Left Column:* **Immutable Decision Records Timeline** (`caisheng.decision.v1` cards with timestamp, SHA-256 cryptographic hash, selected action, and expandable JSON payload).
  * *Right Column:* **Closed-Trade Accounting & P&L Journal** (Realized P&L cards, holding duration, return on risk, exact OCC legs, fees, and slippage).

---

### 3. Screen 2: ⚡ Pro Trading Desk (Interactive Decision Center)
* **Archetype Scenario Selector:** 3 horizontal toggle cards:
  * `NVDA · Long Volatility Archetype`
  * `TSLA · Short Volatility Archetype`
  * `AAPL · Risk Restraint / Stale Feed Veto Archetype`
* **Selected Candidate Header:** Large Ticker (`NVDA`), Spot Price (`$128.50`), and Action Badge (`LONG STRADDLE` / `SHORT IRON BUTTERFLY` / `NO TRADE`).
* **Dialectic Debate Split View (Two Side-by-Side Cards):**
  * *Left Card:* **Long-Vol Specialist Advocate** (Bullish vol thesis, jump catalyst, analyst dispersion, citation links to SEC 10-Q).
  * *Right Card:* **Short-Vol Specialist Skeptic** (IV crush forecast, mean-reverting historical moves, variance risk premium harvest).
* **Model-Risk Critic & OOD Alert:** Confidence score, parameter stability check, quote freshness audit.
* **20-Point Quantitative Risk Gate:** Grid of green/red check badges (Delta Neutrality $\le 2\%$, Wing Balance, Liquidity, No-Arbitrage, Buying Power).
* **Options Payoff Diagram (Plotly Style):** Interactive expiration P&L line (Alpaca Yellow) vs. Post-Earnings Expected Exit with IV crush (Purple dashed line) across spot price shocks ($\pm 15\%$), marking Break-Evens.
* **Alpaca Developer Code Box:** Python snippet with syntax highlighting showing:
  ```python
  # Alpaca Level-3 Multi-Leg Order Intent & Execution Blueprint
  from alpaca.trading.client import TradingClient
  trade_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
  # Target: LONG_STRADDLE · Quantity: 1 unit · Max Stress Loss: $500.00
  ```
* **Non-Bypassable Execution Portal:**
  * `Step 1: Preview Order Plan`
  * `Step 2: Sign Cryptographic Approval Token`
  * `Step 3: Submit Order to Alpaca Paper Broker`

---

### 4. Screen 3: 🧪 Live Paper Canary & FastMCP Playground
* **Private MCP Server Status Card:** Streamable HTTP endpoint `/mcp` and `/healthz` connection indicators; never expose credentials or order submission through the public UI.
* **Market Clock Widget:** Real-time NYSE session countdown (Regular hours vs. AMC earnings window).
* **Live Alpaca Option Chain Explorer:** Interactive table showing strikes, calls/puts, bid/ask spreads, implied volatility, Delta, and Open Interest.
* **Canary Order Sandbox:** Single-contract paper test submission with safety confirmation modal.

---

### 5. Screen 4: ⏪ Historical Forecast Replay
* **Quarterly Event Timeline:** Filter by ticker (`NVDA`, `AAPL`, `TSLA`, `SPY`) across 2024 earnings cycles.
* **Forecast vs. Reality Card:** Pre-event Implied Move vs. Model Forecast vs. Actual Realized Stock Jump.
* **Trade Outcome Summary:** Entry debit/credit, post-event exit price, slippage, and net realized P&L.

---

### 6. Screen 5: 📊 Replay Benchmarks & Controlled Ablation
* **The "30-Second Result" Bar Chart:** High-contrast bar chart comparing Net Executable P&L across:
  * `CaiSheng Full` (Gold)
  * `B3: Ungated Agent` (Red — highlighting policy breaches and bad trades on stale data)
  * `B4: Quant Only` (Blue — statistical baseline without qualitative LLM debate)
* **Component Isolation Highlight Cards:**
  * *Governor Contribution:* Shows where the risk governor prevented catastrophic loss on corrupted feeds.
  * *Agent-Context Contribution:* Shows where LLM debate improved regime detection on identical quant snapshots.
* **Ablation Table & Receipt Export:** Table of all scenarios with a prominent `[ Download Canonical JSON Receipt ]` button.

---

### 7. Screen 6: 📚 Academic Foundations & Research Library
* **Literature Registry Cards:** 6 peer-reviewed papers (Carr-Wu VRP, Patell-Wolfson IV Crush, Rockafellar-Uryasev CVaR, Brenner-Subrahmanyam, Gatheral Rough Vol).
* **Interactive Formula Popovers:** LaTeX equations with direct tags to the platform's backend Python modules.

---

### 8. Screen 7: 🌪️ Rough Volatility Simulator
* **Interactive Quant Controls:** Sliders for Hurst parameter ($H \in [0.05, 0.50]$), mean reversion speed, vol-of-vol, and spot-vol correlation $\rho$.
* **Volatility Smile Comparison Chart:** Plotly curve comparing Rough Volatility power-law skew ($T^{H-1/2}$) against standard Black-Scholes diffusion.
* **Path Signatures Visualizer:** Lyons (1998) coordinate-free tensor series representation.

---

## 📦 Expected Deliverables from Designer
1. **Figma Design File / Mockups** with responsive desktop layout (`1440px` and `1920px`).
2. **Complete Component Library** (Cards, Buttons, Metric Tiles, Status Badges, Code Boxes, Dialectic Debate Split Cards, Payoff Graphs).
3. **Interactive Clickable Prototype** demonstrating:
   * Switching between the 7 tabs.
   * Switching between Ticker Archetypes (`NVDA`, `TSLA`, `AAPL`).
   * The 3-step order preview, approval, and submission flow.
