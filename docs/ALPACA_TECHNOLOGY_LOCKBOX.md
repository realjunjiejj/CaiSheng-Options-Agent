# CaiSheng Alpaca Technology Lockbox

## What it is

The Alpaca Technology Lockbox is CaiSheng's judge-facing proof bundle. It is not
an Alpaca product or API. It demonstrates concrete use of Alpaca's official
agent ecosystem while preserving one non-bypassable order boundary.

```text
Official Alpaca CLI ── read-only account/clock proof ─┐
Official MCP V2 ───── assets + options-data only ─────┼──> sanitized Lockbox receipt
Official skills ───── source + SHA-256 fingerprints ──┘

LangGraph decision ─> deterministic gates ─> canonical approval
                   ─> CaiSheng broker gateway ─> Alpaca Paper Trading API
```

The two paths do not merge into a second order implementation. The official CLI
and official MCP calls used by the Lockbox are reads. CaiSheng's existing broker
gateway remains the sole paper-order mutation path.

## Proof contract

The combined receipt uses schema `caisheng.alpaca-lockbox.v1` and returns `PASS`
only when every component passes.

### Official Alpaca CLI

The verifier:

1. Requires configured credentials and CaiSheng paper mode.
2. Supplies `ALPACA_LIVE_TRADE=false` explicitly and removes `ALPACA_PROFILE`.
3. Runs the installed CLI's `version` and `doctor` commands.
4. Requires diagnostics to resolve exactly
   `https://paper-api.alpaca.markets` and rejects the live endpoint.
5. Performs `account get --quiet` and `clock markets --quiet`.
6. Emits only account status, financial summary, options level, and sanitized
   NYSE clock data.

### Official Alpaca MCP Server V2

The verifier launches `uvx alpaca-mcp-server` over stdio with an environment it
constructs itself:

```text
ALPACA_PAPER_TRADE=true
ALPACA_TOOLSETS=assets,options-data
```

It dynamically lists tools before making a call. Discovery fails if any tool
name indicates order, position, account-configuration, exercise, cancellation,
or another mutation. It then calls only the dynamically discovered `get_clock`
tool. Credentials are passed to the subprocess environment, never command-line
arguments or the receipt.

The `account` MCP toolset is intentionally excluded because it currently
contains an account-configuration write tool. Account connectivity is already
proven by the official CLI read.

### Official Alpaca skills

The verifier requires these project-local files from
`alpacahq/alpaca-skills` and publishes their SHA-256 fingerprints:

* `alpaca-trading-backtest`
* `alpaca-trading-paper-trading`
* `alpaca-trading-paper-trading-cli`
* `alpaca-trading-paper-trading-mcp`

Source paths and hashes are recorded in `skills-lock.json`.

## Run it

From the repository root:

```bash
brew install alpacahq/tap/cli
uvx alpaca-mcp-server --version
uv run python cli.py --lockbox --output-json
```

Or open `01 Command` and click **Verify Official Alpaca Lockbox**.

The local machine running the proof must have paper credentials. The public
credential-free Cloud Run UI is expected to fail this live proof closed; do not
inject paper credentials into a public service merely to make a green badge.
Run the Lockbox locally during judging, or in an authenticated private operator
environment.

## Judge-safe claims

You may say:

> “CaiSheng verified Alpaca's official CLI, dynamically discovered the official
> MCP V2 read-only tool surface, called the paper market clock, and loaded four
> official Alpaca agent skills. Only CaiSheng's approval-bound gateway can place
> a paper order.”

Do not say that Lockbox is an Alpaca product, that its read checks prove trading
profitability, or that a green receipt proves an order was submitted or filled.
