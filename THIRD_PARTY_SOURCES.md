# 📜 Third-Party Sources & Open-Source Attribution

CaiSheng borrows design patterns, data contracts, and architectural paradigms from open-source repositories under permissive licenses (Apache-2.0 and MIT), with attribution and independent implementation.

---

## 🏛️ Open-Source Attribution Registry

| Repository | Upstream Author / Organization | License | Concepts & Architectural Inspirations Adapted |
| :--- | :--- | :--- | :--- |
| **[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)** | Tauric Research (*Xiao et al.*) | Apache-2.0 | Multi-agent dialectic debate state, LangGraph orchestration, opposing research advocates, model-risk critic supervision, and structured decision handoffs. Translated from directional equity picking to non-directional event volatility. |
| **[anthonymakarewicz/volatility-trading](https://github.com/anthonymakarewicz/volatility-trading)** | Anthony Makarewicz | MIT | Options surface data contracts, point-in-time quote quality control stages, bid/ask spread friction modeling, and ATM strike selection. |
| **[lambdaclass/options_portfolio_backtester](https://github.com/lambdaclass/options_portfolio_backtester)** | LambdaClass | MIT | Independent cash-flow accounting oracles, multi-leg payoff convexity tests, and reproducible dataset hash manifests. |
| **[alpacahq/alpaca-py](https://github.com/alpacahq/alpaca-py)** | Alpaca Securities LLC | Apache-2.0 | Level-3 Multi-Leg Option Order (`OptionOrderRequest`) serialization, per-leg `position_intent` enums, paper API endpoint configuration, and execution reconciliation. |
| **[alpacahq/cli](https://github.com/alpacahq/cli)** | Alpaca | Apache-2.0 | Official agent-first CLI used at runtime for fail-closed paper-endpoint diagnostics and sanitized account/clock verification. |
| **[alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server)** | Alpaca | MIT | Official FastMCP/OpenAPI V2 server launched at runtime with dynamic discovery and the restricted `assets,options-data` tool surface. |
| **[alpacahq/alpaca-skills](https://github.com/alpacahq/alpaca-skills)** | Alpaca | Apache-2.0 | Unmodified official backtest and paper-trading agent instructions for generic, CLI, and MCP workflows; source paths and fingerprints are recorded in `skills-lock.json`. |

---

## 🔒 Attribution & Independence Policy

1. **No Proprietary Leaks:** CaiSheng contains zero proprietary trading algorithms or internal market-maker source code. All concepts are derived strictly from publicly available academic research papers and open-source packages.
2. **Deterministic Trust Boundaries:** All quantitative pricing math, risk gate evaluations, and order submissions are implemented deterministically in pure Python without black-box third-party dependencies.
