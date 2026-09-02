# CaiSheng Judge-Facing Design System

## Product and audience

CaiSheng is an autonomous options-alpha agent for the Alpaca hackathon. Its UI is a judge-facing proof surface, not a marketing site and not a retail brokerage. A judge should understand within 30 seconds:

1. Is the $100,000 Alpaca paper account connected and safe?
2. What opportunity did the agent find, and why does it expect positive P&L?
3. Which multi-agent and deterministic risk checks approved or rejected it?
4. What order was or will be sent through Alpaca?
5. What live and historical evidence supports the strategy?

Every displayed state must map to a real Streamlit/backend capability. Do not invent authentication, connectivity, orders, P&L, positions, timestamps, events, forecasts, or API receipts.

## Information architecture

Use four primary destinations only:

- **Command** — authoritative Alpaca paper NAV, buying power/equity, competition P&L, reserved risk, circuit breaker, positions, recent decisions, reconciliation and MCP/CLI proof.
- **Agent** — the multi-agent decision trace: event and market snapshot, implied move versus forecast move, long-vol advocate, short-vol advocate, critic, deterministic risk gates, selected defined-risk structure, payoff and approval state. Replay examples must be visibly labelled `SEALED REPLAY`.
- **Paper Trade** — the live Alpaca canary workflow: verified event inputs, fresh-data state, risk-governor outcome, immutable one-unit plan, explicit approval and paper-only submission. Never imply that a disabled action ran.
- **Evidence** — historical pre-event forecast replay and controlled ablation scoreboard, with clear labels distinguishing bar-proxy, synthetic replay, and live out-of-sample results.

Academic papers, formulas, rough-volatility experiments, raw JSON, and long logs are supporting detail. Place them inside an `Evidence & Methodology` drawer or contextual inspector; do not make them primary navigation tabs.

## Navigation and interaction truth

- Use a compact sticky application header, not a marketing-site hero.
- Brand identity is text-only: `CaiSheng` with the qualifier `ALPACA PAPER · OPTIONS ALPHA`. No invented logo, generic icon mark, login button, or connect-API button.
- The active primary destination must be unmistakable.
- Buttons must correspond to implemented actions only: run preflight, reconcile, run sealed replay scenario, run live canary, lock forecast, reveal/score outcome, approve immutable plan, submit paper order, inspect receipt, download receipt.
- Do not add `Initialize Sequence`, `View Whitepaper`, `Login`, or `Connect API` because these are not backed by the current app.
- Disabled and fail-closed states are first-class. Explain the exact reason next to the disabled action.

## Visual direction

An institutional operations terminal with Alpaca energy: precise, compact, and high contrast. Avoid a generic SaaS dashboard, a Bloomberg imitation, excessive glassmorphism, giant marketing typography, or decorative liquid waves that push evidence below the fold.

### Color tokens

- Canvas: `#07090D`
- Primary surface: `#0C0F14`
- Raised surface: `#141820`
- Border: `#252C38`
- Primary text: `#FFFFFF`
- Secondary text: `#9DA7B3`
- Muted text: `#6B7785`
- Alpaca yellow / primary action: `#FFD000`
- Profit/pass: `#00C805`
- Loss/fail: `#FF3366`
- Live-data accent: `#00E5FF`
- Volatility accent: `#A855F7`

Use yellow sparingly for the single most important action or state. Never color every card yellow. Green and red describe verified state, never decoration.

### Typography

- UI and narrative: `Inter`, system sans-serif fallback.
- Numbers, timestamps, hashes, contract symbols and receipts: `JetBrains Mono`, monospace fallback.
- Do not introduce Cabinet Grotesk, serif fonts, decorative display fonts, or additional families.
- Page title: 28–36 px, dense and functional.
- Section title: 18–24 px.
- Metric: 24–32 px mono.
- Labels: 11–13 px, uppercase only when scanning benefits.

### Shape, spacing and elevation

- Main content max width: 1440 px.
- 12-column desktop grid; stack intentionally on smaller viewports.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48 px.
- Cards: 12–16 px radius, not 32–120 px.
- Pills only for compact state labels, not every control.
- Borders do most grouping work. Shadows are subtle; no glowing neon or decorative blur orbs.
- Prefer one dense screen with progressive disclosure over multiple long scrolling marketing sections.

## Command view hierarchy

Above the fold:

1. Header: brand, `PAPER` environment, market session, Alpaca/API health, last refresh.
2. Competition strip: starting NAV fixed at $100,000; current equity; net P&L and return; buying power; reserved risk versus 2% cap; circuit breaker.
3. Primary action row: `Run Agent Scan` or selected existing action; `Run Preflight`; `Reconcile`; kill-switch state.
4. Main two-column workspace:
   - Left 7 columns: opportunity/decision card with symbol, event, data mode, implied versus forecast move, probability/edge, chosen action and payoff.
   - Right 5 columns: risk governor, approval state, executable Alpaca paper order summary, receipt state.
5. Lower evidence row: positions/P&L, immutable decision records, latest MCP/CLI receipts.

Empty, loading, stale, rejected, halted and no-trade states must be visually complete and truthful.

## Agent decision view hierarchy

- Always show `LIVE ALPACA`, `SEALED REPLAY`, `BAR-PROXY`, or `SYNTHETIC REPLAY` near the title.
- Do not hard-code NVDA as the product identity. A sample scenario may show a ticker, but it must be labelled as the currently selected replay.
- Put the quantitative comparison first: implied move, forecast median and interval, probability move exceeds implied, expected IV change/crush, liquidity and data freshness.
- Show the debate as a compact three-stage trace: Long-Vol Advocate, Short-Vol Advocate, Model-Risk Critic. The deterministic governor remains visually separate and final.
- The final answer is one of `LONG STRADDLE`, `SHORT IRON BUTTERFLY`, or `NO TRADE`.
- Show exact option legs, expiry, strike, side, quantity, bid/ask/limit, max loss, Greeks and break-evens only when available.

## Evidence view hierarchy

- Lead with the 30-second result chart and honest dataset labels.
- Separate `live OOS`, `historical bar-proxy`, and `synthetic functional ablation` results.
- Show sample size, coverage, forecast error, calibration, executable/proxy P&L, drawdown, risk breaches and abstention rate when present.
- Never call synthetic replay statistical proof of alpha.
- Keep scenario-level tables, methods, formulas, citations and downloadable JSON behind expanders.

## Motion and feedback

- Use motion only for data refresh, progress through the agent graph, and new receipt arrival.
- 120–180 ms transitions; respect reduced-motion settings.
- No continuous floating, tilting, pulsing or rotating cards. A small status pulse is allowed only for a genuinely active live process.

## Accessibility and judge usability

- Minimum 4.5:1 contrast for body text.
- Never encode pass/fail only by color; include icon and text.
- Tables must have readable headers and horizontal overflow handling.
- Important figures must include units and data-mode/source labels.
- The first screen must remain legible on a 1366×768 projector/laptop viewport.

## Hard prohibitions

- No unsupported top-level tabs.
- No fake live connectivity or fake P&L.
- No stale/expired contract presented as executable.
- No marketing CTAs with no handler.
- No invented logo or non-existent user account system.
- No giant hero that hides the trading proof.
- No source-code block as the principal evidence of Alpaca integration; show actual action/receipt states instead.
- Use ONLY the fonts, colors, spacing, and component styles defined here and in `src/volagent/ui/theme.py`.
