# CaiSheng — Sealed NVDA Earnings Volatility Prediction

## Scope

This is a **pre-event, analysis-only** volatility forecast captured before NVIDIA's FY27 Q2 earnings release. It is not investment advice and no Alpaca order was submitted.

- Official event source: <https://investor.nvidia.com/events-and-presentations/events-and-presentations/event-details/2026/NVIDIA-2nd-Quarter-FY27-Financial-Results/default.aspx>
- Event: NVIDIA FY27 Q2 results, after market close
- Event time: 2026-08-26 21:00 UTC (2026-08-27 05:00 SGT)
- Forecast decision time: 2026-08-26 15:09:16 UTC (2026-08-26 11:09:16 ET)
- Declared evaluation time: 2026-08-27 21:00 UTC (2026-08-28 05:00 SGT)
- Broker: Alpaca paper account only
- Order-submission kill switch: `false`
- Orders submitted for this forecast: `0`

## Live Inputs

| Input | Value |
|---|---:|
| NVDA spot | $211.25 |
| Validated live option contracts | 42 filtered from 192 raw contracts |
| ATM call/put pair | Present |
| Verified prior earnings reactions | 4 |
| Historical median absolute earnings move | 2.445% |
| Realized volatility, 10-day | 22.874% annualized |
| Realized volatility, 30-day | 36.019% annualized |

## Prediction

| Forecast | Value |
|---|---:|
| Market-implied absolute move baseline | **5.680%** (about $12.00) |
| Historical-median move baseline | **2.445%** |
| VolAgent median absolute-move forecast | **4.453%** (about $9.41) |
| VolAgent 20th-percentile move | **3.117%** |
| VolAgent 80th-percentile move | **6.235%** |
| Probability realized move exceeds market-implied move | **25.43%** |
| Forecast edge: model minus implied move | **-1.227 percentage points** |
| Expected post-event ATM IV change | **-52.90 IV points** |

## Decision

`NO_TRADE`

The model expects a meaningful earnings move, but less movement than the options market prices. The short-vol advocate was stronger, but no candidate retained a non-negative risk-adjusted score after tail penalties. The critic passed; the deterministic risk governor rejected execution on the `positive_score` gate.

## Tomorrow's Objective Scorecard

At or after the declared evaluation time, use fresh Alpaca quotes to calculate:

1. **Realized absolute move**

   `abs(exit spot / $211.25 - 1)`

2. **Movement forecast errors**

   - VolAgent error: `abs(realized move - 4.453%)`
   - Market-implied baseline error: `abs(realized move - 5.680%)`
   - Historical-median baseline error: `abs(realized move - 2.445%)`

   VolAgent wins this event only if its error is lower than both baselines.

3. **Interval coverage**

   The event is inside the forecast interval only if the realized absolute move is between **3.117%** and **6.235%**.

4. **IV-crush error**

   Compare the fresh post-event ATM IV change with the predicted **-52.90 IV points**.

5. **Decision quality**

   This event's actual VolAgent paper P&L is **$0.00** because it abstained. Compare that result with counterfactual always-long-straddle and defined-risk short-vol baselines using identical quotes, fees, and slippage. Do not claim alpha from this single event.

## Interpretation Guardrail

This forecast is one out-of-sample observation, not proof of predictive skill. The current ticker history contains only four verified prior earnings observations. Evaluate the same scorecard across at least 30–50 events, including abstentions, before making a calibration or alpha claim.
