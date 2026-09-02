# Shared Layout Components

## 1. Top App Shell & Alpaca Yellow Hero Header

### Source File: `app.py` (Header section)
Renders the full-width Alpaca Yellow Hero Banner containing branding, live status pills, and portfolio mandate.

```html
<div class="alpaca-hero-banner">
    <div class="alpaca-nav-bar">
        <div class="alpaca-brand-title">
            <span style="font-size: 1.3em;">🦙</span>
            <span>Alpaca</span>
            <span style="font-weight: 400; opacity: 0.45; margin: 0 4px;">/</span>
            <span style="font-weight: 800; color: #000000;">CaiSheng Options Alpha</span>
        </div>
        <div class="alpaca-nav-links">
            <span class="alpaca-nav-pill">PAPER TRADING: $100,000.00</span>
            <span class="alpaca-nav-pill">LEVEL-3 MLEG API</span>
            <span class="alpaca-nav-pill">FASTMCP READY</span>
            <span class="alpaca-nav-pill" style="background: rgba(0, 0, 0, 0.85); color: #FFFFFF;">GATEWAY: CLEAN</span>
        </div>
    </div>
    <div class="alpaca-hero-heading">
        API for Stock, Options, Crypto Trading & more
    </div>
    <div class="alpaca-hero-sub">
        Autonomous multi-agent volatility trading system built natively on Alpaca's Level-3 Options API.
        Harnessing dialectical AI debate, rough volatility modeling, and non-bypassable risk gates.
    </div>
    <div style="display: flex; gap: 14px; align-items: center; flex-wrap: wrap;">
        <div class="alpaca-hero-cta">
            ⚡ $100,000 Portfolio Mandate Active
        </div>
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82em; font-weight: 700; color: rgba(0, 0, 0, 0.75);">
            • Fail-Closed Execution Gateway • Defined Risk Hard Cap (1.0% NAV) • Zero Directional Bias
        </span>
    </div>
</div>
```

---

## 2. Navigation Tab Bar

### Source: `app.py`
```python
tab_cockpit, tab_desk, tab_canary, tab_historical, tab_benchmarks, tab_research, tab_rough_vol = st.tabs([
    "🏛️ Capital Command",
    "⚡ Pro Trading Desk",
    "🧪 Live Paper Canary",
    "⏪ Historical Forecast Replay",
    "📊 Replay Benchmarks",
    "📚 Academic Foundations",
    "🌪️ Rough Volatility Simulator",
])
```
