# CaiSheng Execution Incident — Remediation Record

## Executive finding

A pre-hardening Streamlit block in `src/volagent/ui/pages/cockpit.py` created its own `TradingClient`, hard-coded four underlyings and strikes, derived multi-contract quantities from a dollar budget, and called Alpaca `submit_order` directly. It bypassed the canonical ledger, DecisionRecord, one-contract limit, portfolio allocator, risk governor, duplicate protection, reconciliation boundary, and autonomous lifecycle.

This was an execution-boundary defect. The affected broker positions must not be described as governed CaiSheng trades unless matching canonical lineage exists.

## Observed account impact

Read-only Alpaca inspection on 2026-09-01 observed:

- Starting mandate NAV: `$100,000.00`
- Account equity at inspection: approximately `$88,268.10`
- Full-account P&L: approximately `-$11,731.90`
- Twelve long option legs across six underlyings
- Approximate option premium/cost basis: `$88,050`
- Approximate unrealized position P&L: `-$8,526`
- Expiration: 2026-09-02 for the observed contracts
- Canonical ledger: only the earlier one-unit SPY canary and a rejected SPY attempt; the large basket was not represented as governed exposure

These are point-in-time observations, not fixed report values. The live UI must always use fresh Alpaca state.

## Remediation completed

1. Deleted the direct Streamlit basket executor and its raw `TradingClient` use.
2. Added a repository invariant: only `src/volagent/execution/alpaca.py` may contain `.submit_order(`.
3. Added mandatory broker-to-ledger reconciliation before every new paper entry.
4. Kept risk-reducing close orders available during a system halt.
5. Fixed Alpaca signed position quantities so short quantities are not double-negated.
6. Normalized plain and SDK enum sides such as `short` and `PositionSide.SHORT`.
7. Stopped terminal historical orders from causing permanent orphan-order halts; live positions remain authoritative for filled exposure.
8. Added the broker-authoritative Risk Envelope with `NORMAL`, `LIQUIDATE_ONLY`, and `UNVERIFIED` modes.
9. Added full-account net P&L and return to the canonical economic receipt.
10. Kept governed closed-trade P&L as a separately labelled subset.
11. Changed the Evidence ladder so full-account P&L is the Alpaca headline and unattributed/unrealized activity is not claimed as alpha.
12. Added exact presenter language and safe fallback behavior in `docs/JUDGE_LIVE_DEMO_SCRIPT.md`.

## Required recovery procedure

No autonomous entry is permitted until all steps pass:

1. Cancel any untracked active opening orders.
2. Decide how to manage each existing position; do not close positions merely to improve presentation optics.
3. Use exact-contract, risk-reducing closing orders only with explicit human authorization.
4. Confirm broker positions after every fill or partial fill.
5. Reconcile broker and ledger.
6. Resolve or formally quarantine every orphan position.
7. Confirm Risk Envelope `NORMAL`.
8. Confirm account ID matches immutable competition metadata.
9. Confirm the one-contract, `$500` hard-loss, one-entry-per-day, aggregate-risk, daily-loss, and drawdown gates.
10. Re-arm the short-lived competition lease only after the account is clean.

## Claim policy for judging

- Report the full Alpaca account result even when it is negative.
- Report governed P&L separately.
- Do not call the untracked basket an autonomous CaiSheng decision.
- Do not reset or replace the competition account to remove the loss.
- Explain the failure and containment only if asked or if the live Risk Envelope displays the discrepancy.
- Use a separate paper account for future destructive development testing, subject to the competition rules.
