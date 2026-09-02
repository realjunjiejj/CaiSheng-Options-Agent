# CaiSheng Live Alpaca Paper Test — 2026-08-31

## Executive result

**Test verdict:** PASS — the system authenticated against Alpaca Paper, reconciled cleanly, enforced the $100,000 mandate, and failed closed before the configured trading window.

**Profitability verdict:** NOT YET MEASURABLE — no broker-confirmed trade was opened or closed during this test.

This receipt must not be described as proof of profitable trading.

## Test conditions

| Field | Observed result |
|---|---:|
| Local test time | 2026-08-31 21:24–21:25 SGT |
| UTC test time | 2026-08-31 13:24–13:25 UTC |
| Broker environment | Alpaca Paper |
| Paper account | `…4ee4` |
| Starting mandate NAV | $100,000.00 |
| Current equity | $100,000.00 |
| Cash | $100,000.00 |
| Buying power | $400,000.00 |
| Competition authorization | DISARMED |
| Market state observed by lifecycle | CLOSED |
| CaiSheng daily scan window | 10:15–14:30 ET / 22:15–02:30 SGT |
| System halt | None |
| Authoritative ledger | `data/runtime/competition_ledger.db` |

## Alpaca preflight

Overall status: **CLEAN**

- Paper endpoint enforcement: PASS
- Authenticated account access: PASS
- Required $100,000 starting NAV: PASS
- Competition-account binding: PASS
- Persistent system-halt check: PASS

The test used Alpaca's paper endpoint. No real money was involved.

## Broker reconciliation

Overall status: **CLEAN**

| Reconciliation item | Count |
|---|---:|
| Matched orders | 0 |
| Matched positions | 0 |
| Orphan broker orders | 0 |
| Orphan broker positions | 0 |
| Orphan ledger positions | 0 |
| Quantity mismatches | 0 |

Reconciliation receipt: `rec-2368c1de5b`

Preflight, reconciliation, lifecycle, and economic-evidence generation were rerun against the same authoritative competition ledger. This prevents an apparently clean result from being assembled across different local databases.

## Lifecycle run result

The competition lifecycle was run in **preview mode** with the competition configuration and persistent project-local ledger.

| Lifecycle field | Result |
|---|---:|
| Market open | False |
| Eligible events found | 0 |
| Agent decisions generated | 0 |
| Benchmark intents locked | 0 |
| Order previews created | 0 |
| Submission attempts | 0 |
| Entries submitted | 0 |
| Positions monitored | 0 |
| Lifecycle errors | 0 |

This is the correct outcome because the run occurred before the U.S. regular session and before CaiSheng's configured 10:15 ET opportunity window. The agent did not invent a quote, decision, benchmark, or order to make the demonstration appear active.

## P&L result

### Competition P&L — authoritative

| Metric | Result |
|---|---:|
| Broker-confirmed closed trades | 0 |
| Realized Alpaca paper P&L | **$0.00** |
| Return on starting NAV | 0.000% |
| Win rate | Not available |
| Profit factor | Not available |
| Maximum drawdown | $0.00 |

Status: `AWAITING_BROKER_CONFIRMED_CLOSED_TRADES`

### Evidence that is not competition P&L

- Controlled synthetic replay: +$2,044.00 across four synthetic trades.
- Historical predictive validation: 38 evaluated events; verdict remains **promising but statistically unproven**.
- Agent historical MAE: 4.573%.
- Implied-move benchmark MAE: 4.452%.
- Agent win rate versus implied move: 47.37%.

The synthetic and historical figures are research evidence only. They are not added to the $0.00 Alpaca competition result.

Economic-evidence receipt SHA-256:

`3a09100b312149977496eed39f3d56063eb570f7afa8b886939f8187485211b5`

## What was proven

1. Alpaca Paper credentials and account access work.
2. The competition account begins at the required $100,000.
3. The broker and SQLite ledger agree that there are no orders or positions.
4. The lifecycle respects the exchange/strategy window.
5. Disarmed competition mode cannot submit an order.
6. No shadow, replay, or historical result is misreported as broker P&L.

## What remains to be tested

The first economically meaningful test should run at or after **22:15 SGT on 2026-08-31**, when the configured SPY/QQQ/IWM opportunity window opens.

Required sequence:

1. Re-run preflight immediately before the scan.
2. Arm the time-limited paper-only competition lease.
3. Run one autonomous opportunity scan.
4. Verify that at most one defined-risk order is submitted.
5. Record the Alpaca entry order ID and fill.
6. Confirm all seven shadow policies were locked before the outcome.
7. Monitor and close the paper position according to the lifecycle rules.
8. Reconcile the entry and exit against Alpaca.
9. Report realized P&L only after a broker-confirmed close.
10. Settle the shadow benchmarks from their common locked exit timestamp.

## Final claim

> At 21:24–21:25 SGT on 2026-08-31, CaiSheng passed live Alpaca Paper connectivity, mandate, reconciliation, and fail-closed lifecycle checks. It submitted no order because the market/window and authorization gates were not satisfied. Broker-confirmed competition P&L remains $0.00 from zero closed trades.
