# CaiSheng — Submission Packet

Use this file as the single source of truth for the hackathon form. Replace only the two fields marked `REQUIRED HUMAN INPUT` immediately before submission.

## Basic information

### Project title

**CaiSheng — Auditable Multi-Agent Options Alpha**

### Short description

CaiSheng is a paper-only options-volatility agent that debates long versus short volatility, applies deterministic risk gates, and routes approved defined-risk multi-leg orders through Alpaca.

### Long description

CaiSheng scans confirmed earnings events and liquid `SPY/QQQ/IWM` volatility opportunities in a `$100,000` Alpaca paper account. Its LangGraph workflow compares executable option-implied movement with a strongly shrunk forecast, creates opposing long- and short-volatility theses, and sends them to a model-risk critic. Deterministic code—not an LLM—owns pricing, expected value, contract selection, sizing, the 20-point risk governor, and execution eligibility. The only permitted outcomes are an ATM long straddle, a defined-risk short iron butterfly, or `NO_TRADE`.

The execution layer uses Alpaca market data and Trading API account, position, order, option-chain, Level-3 multi-leg, cancellation, and reconciliation capabilities. A judge-facing Lockbox verifies Alpaca's official CLI, official MCP Server V2, and four official agent skills while preserving one policy-enforced write gateway. Every decision and order intent is hashed and persisted, and every broker-confirmed trade links its thesis, maximum risk, exact contracts, entry/exit order IDs, and realized P&L.

CaiSheng never presents replay as competition performance. The controlled `+$2,044` result is four-trade synthetic functional evidence; the submitted Alpaca paper account ID is the authority for competition P&L.

### Technology and category tags

`Alpaca Trading API`, `Alpaca MCP`, `Alpaca CLI`, `Alpaca Skills`, `LangGraph`, `FastMCP`, `Options`, `Multi-Agent`, `Python`, `Streamlit`, `Google Cloud`, `Paper Trading`, `Risk Management`

## Cover image and presentation

- Cover image: [`../submission/CaiSheng_Cover.png`](../submission/CaiSheng_Cover.png)
- 90-second video: [`../submission/CaiSheng_Judge_Pitch_90s.mp4`](../submission/CaiSheng_Judge_Pitch_90s.mp4)
- Slide deck: [`../submission/CaiSheng_Judge_Deck.pptx`](../submission/CaiSheng_Judge_Deck.pptx)
- One-page write-up: [`ONE_PAGE_WRITEUP.md`](ONE_PAGE_WRITEUP.md)
- Live-demo script: [`JUDGE_LIVE_DEMO_SCRIPT.md`](JUDGE_LIVE_DEMO_SCRIPT.md)

## App hosting and repository

- Public GitHub repository: **https://github.com/realjunjiejj/CaiSheng-Options-Agent**
- Demo platform: **Google Cloud Run — credential-free, read-only judge UI.**
- Application URL: **https://caisheng-ui-34syptghka-uc.a.run.app**
- Alpaca paper trading account ID: **f58cdc6f-edda-438f-9614-c5fe317b996c**

## Claim-safe judging summary

### 1. P&L performance

- Starting mandate: `$100,000`.
- Risk target: `$250` per strategy.
- Hard trade-risk cap: `$500` / `0.5%` NAV.
- Daily-loss halt: `$500`.
- High-water drawdown halt: `1%`.
- Actual competition result: read from the submitted Alpaca paper account at judging time.
- Read-only verification on 2026-09-02: `$100,000` equity, `$100,000` cash, `$400,000` buying power, `0` open positions, and `$0` full-account P&L versus the mandate baseline.
- Governed CaiSheng P&L: count only broker-confirmed entry-to-exit lifecycles with entry and exit order IDs.
- Controlled replay: `+$2,044` over four synthetic trades; functional evidence only, not a backtest or competition P&L.

### 2. Technology implementation

- Alpaca Trading API for account, positions, orders, market clock, option chains, Level-3 MLEG paper orders, cancellation, and reconciliation.
- Alpaca official CLI verification against the paper endpoint.
- Alpaca official MCP Server V2 with dynamically discovered read-only `assets,options-data` tools.
- Four fingerprinted official Alpaca skills.
- CaiSheng FastMCP gateway accepting only persisted, approved canonical order tokens.
- One non-bypassable `submit_order` boundary, durable order intents, idempotency, and two-way reconciliation.

### 3. Creativity and originality

- Non-directional volatility thesis anchored to executable option-implied movement.
- Adversarial long-volatility versus short-volatility reasoning plus an independent critic.
- Agent-runtime receipts distinguish structured LLM inference, deterministic synthesis, and fallback.
- Neuro-symbolic boundary: agents explain and challenge; deterministic math controls economics and safety.

### 4. Presentation and execution

- Public judge UI exposes only credential-free `Agent` and `Evidence` workspaces.
- Private operator UI retains account, paper order, autonomy, monitoring, and emergency controls.
- The first evidence screen answers: what was traded, why, maximum risk, and result.
- Every displayed P&L carries an evidence label: Alpaca paper, historical bar proxy, or synthetic replay.

## Final submission gate

- [x] Project title, descriptions, and tags are drafted.
- [x] Cover image exists and has been visually verified.
- [x] 90-second video exists, is 1920×1080, and its corrected key frames were inspected.
- [x] Seven-slide deck exists, contains source notes, renders without overflow, and every slide was inspected.
- [x] One-page AI logic, risk, and Alpaca infrastructure write-up exists.
- [x] Public Cloud Run mode has no credentials, account controls, or order controls.
- [x] The physically sanitized public image builds locally and passes its Streamlit health check.
- [x] Full test suite passes locally.
- [ ] Public GitHub repository URL entered.
- [x] Public Cloud Run HTTPS URL deployed and smoke-tested.
- [ ] Exact Alpaca paper competition account ID entered.
- [ ] Submission-time account P&L read directly from Alpaca and stated without mixing replay evidence.
