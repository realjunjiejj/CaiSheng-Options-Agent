# CaiSheng — Canonical Live Judge Demo Script

## Non-negotiable claim policy

This is the only presentation script to use for the hackathon.

- **Full Alpaca account P&L** = current verified paper equity minus the immutable `$100,000` starting NAV. This is the headline account truth.
- **Governed closed-trade P&L** = only completed entry/exit lifecycles whose Alpaca broker IDs are recorded in CaiSheng's ledger.
- **Replay P&L** = controlled synthetic evidence. It is never competition P&L or proof of alpha.
- **Historical forecast results** = predictive validation, not executable fill evidence.
- Never call untracked broker activity a CaiSheng trade. Never hide a loss by resetting or switching accounts.
- Never submit an order during the demo unless the Risk Envelope is `NORMAL`, reconciliation is `CLEAN`, the lease is `ARMED`, the market is open, and the approved quantity is exactly one.

## Presenter setup — complete 20 minutes before judging

1. Start the app from the repository root:

   ```bash
   .venv/bin/streamlit run app.py
   ```

2. Select `01 Command`.
3. Confirm the header says `PAPER ONLY · FAIL CLOSED`.
4. Confirm `Initial Mandate NAV` is `$100,000.00`.
5. Do **not** clear the ledger, delete the account, reset its balance, or create a replacement competition account to improve the displayed result.
6. Keep `VOLAGENT_ALLOW_ORDER_SUBMISSION` absent from the Streamlit process. A value stored in `.env` cannot arm writes; CaiSheng now requires an explicit process-scoped value plus a valid competition lease.
7. Click `Run CaiSheng Preflight`, `Reconcile Alpaca`, `Verify Guarded MCP`, and `Verify Official Alpaca Lockbox` once. Keep the successful sanitized receipts in the Streamlit session.
8. Record the state you actually see:
   - Full Alpaca account P&L: `____________`
   - Governed closed-trade P&L: `____________`
   - Risk Envelope mode: `____________`
   - Broker legs / governed legs: `____________ / ____________`
   - Reconciliation status: `____________`
9. Open `02 Agent` and preselect `AAPL · Risk Restraint Archetype`.
10. Open `03 Paper Trade` once so fresh-data latency is known. Do not submit.
11. Open `04 Evidence` once so the sealed replay cache is warm.

If any live call fails, do not improvise a success claim. Say: “The live dependency is unavailable, so CaiSheng has failed closed. I will show the cached, clearly labelled engineering evidence.”

---

## Primary live demo — 3 minutes 30 seconds

### 0:00–0:22 — One-sentence thesis

**Screen:** `01 Command`, top viewport.

**Point to:** `$100,000 PAPER MANDATE`, `PAPER ONLY · FAIL CLOSED`, current equity.

**Say exactly:**

> “CaiSheng is an autonomous Alpaca options agent that searches for volatility mispricing, debates long versus short volatility in LangGraph, and allows deterministic risk code—not an LLM—to size, approve, submit, monitor, and reconcile every paper trade.”

**Judge criterion:** Creativity & Originality.

### 0:22–0:52 — Lead with economic truth

**Screen:** Stay on `01 Command`.

**Point to:** `Initial Mandate NAV`, `Current Equity`, and then the `Broker-Authoritative Risk Envelope`.

**Say exactly:**

> “The competition baseline is fixed at one hundred thousand dollars. The full-account result on screen is the broker truth: current Alpaca equity minus that baseline. Beside it, governed closed-trade P&L counts only complete CaiSheng lifecycles with both Alpaca entry and exit IDs. I do not mix either number with replay.”

If the full account is negative, add:

> “The account is currently negative. I will not relabel, reset, or hide it. The technical contribution I can prove is that CaiSheng now detects whether exposure has canonical provenance and stops adding risk when it does not.”

**Judge criterion:** P&L Performance and credibility.

### 0:52–1:20 — Live containment proof

**Point to:** `ENTRY MODE`, `EXPOSURE PROVENANCE`, `GROSS MARKED EXPOSURE`, violations.

If the mode is `LIQUIDATE_ONLY`, say:

> “The Risk Envelope is live and broker-authoritative. Alpaca currently contains exposure without matching CaiSheng decision and order receipts, so the system is in LIQUIDATE ONLY. New autonomous entries are impossible, but exact-contract risk-reducing exits remain available. This is the correct response to an account-state discrepancy.”

If the mode is `NORMAL`, say:

> “The Risk Envelope is live and broker-authoritative. Every open broker leg is matched to a canonical CaiSheng intent, the account is inside its drawdown and quantity limits, and new entries may proceed only through the one gateway.”

If the mode is `UNVERIFIED`, say:

> “Alpaca state is not currently verifiable, so CaiSheng refuses new entries. It never substitutes cached account data for a live risk decision.”

**Do not say:** “The risky positions were chosen by the agent” unless matching DecisionRecords and order receipts exist.

### 1:20–1:47 — Reconciliation and non-bypassable execution

**Action:** Click `Reconcile Alpaca`.

**Say exactly while the receipt appears:**

> “This compares Alpaca orders and positions against the SQLite execution ledger in both directions. Active orphan orders, orphan positions, missing legs, quantity mismatches, and unknown submissions halt entries. Historical terminal orders remain audit evidence but do not create a permanent false halt.”

Then say:

> “There is now exactly one source file permitted to call Alpaca submit-order. The UI, LangGraph agents, MCP server, scanner, allocator, and lifecycle runner cannot call Alpaca directly. A repository invariant test enforces that boundary.”

**Judge criterion:** Technology Implementation.

### 1:47–2:12 — Alpaca ecosystem live proof

**Action:** Click `Verify Official Alpaca Lockbox`.

**Point to:** Official CLI, Official MCP V2, Official Skills, Order Boundary.

**Say exactly:**

> “This sanitized Lockbox proves our use of Alpaca's official CLI, MCP Server V2, agent skills, Trading API, and Market Data API. The sponsor MCP proof is intentionally read-only. CaiSheng's guarded MCP write tool can only load an already-approved immutable order from the ledger and route it through the same canonical gateway.”

**Action:** Click `Verify Guarded MCP` only if the first receipt completes promptly.

**Say:**

> “Secrets, account identifiers, and raw broker payloads are recursively removed before judge display.”

**Judge criterion:** Technology Implementation.

### 2:12–2:48 — Multi-agent decision and mathematical rigor

**Action:** Select `02 Agent`, then `AAPL · Risk Restraint Archetype`.

**Point to:** implied move, forecast move, long-vol advocate, short-vol advocate, critic, risk result.

**Say exactly:**

> “This is a sealed replay, visibly isolated from live execution. LangGraph runs event and volatility analysis in parallel, then long-vol and short-vol advocates in parallel, followed by an independent model-risk critic. The option market's implied move is the anchor. A learned residual correction is allowed only when walk-forward evidence supports it.”

> “Deterministic code recomputes implied move, expected value after spread and slippage, maximum loss, Greeks, stress loss, liquidity, quote freshness, topology, and portfolio limits. The AAPL case abstains because preserving capital is a valid autonomous action.”

**Judge criterion:** Creativity & Originality and quantitative rigor.

### 2:48–3:12 — Fresh Alpaca analysis without unsafe theatre

**Action:** Select `03 Paper Trade`.

**Say exactly:**

> “Paper Trade cannot reuse replay contracts. It requests fresh Alpaca underlying and option snapshots, selects an exact common-strike structure, validates timestamps and liquidity, and produces either a one-unit approved plan or no trade. I will not press submit unless the live Risk Envelope, reconciliation, lease, market clock, and edge gates all pass.”

If the market is closed or the agent abstains, say:

> “No trade is the live result. That is evidence of autonomy with restraint, not a broken demo.”

If all gates pass, stop before the final submit control unless the competition demonstration explicitly authorizes an order.

**Judge criterion:** Autonomous trading behavior.

### 3:12–3:30 — Four answers and close

**Action:** Select `04 Evidence`.

**Point to:** the four-answer trade tape and Alpaca evidence row.

**Say exactly:**

> “The judge can answer four questions in one screen: what CaiSheng traded, why it traded, maximum dollars at risk, and broker-confirmed result. Full-account P&L, governed P&L, historical forecasts, and synthetic replay remain separate. CaiSheng's advantage is not a prettier prediction—it is selective volatility reasoning joined to a broker-verifiable autonomous lifecycle.”

---

## 60-second fallback

**Screen sequence:** `01 Command` → `02 Agent` → `04 Evidence`.

> “CaiSheng is a LangGraph multi-agent volatility trader for Alpaca's one-hundred-thousand-dollar paper mandate. This first number is the full Alpaca account result; the governed result counts only closed CaiSheng trades with broker entry and exit IDs. The live Risk Envelope matches broker positions to canonical decisions and switches to LIQUIDATE ONLY on orphan exposure, drawdown, excess quantity, or an active halt. Only one gateway can call Alpaca submit-order, and a test scans the repository to enforce it. Here, long-vol and short-vol agents debate while deterministic code owns implied move, EV after costs, maximum loss, liquidity, stress, and sizing. This Evidence screen answers what it traded, why, risk, and result, while keeping replay separate from competition P&L.”

---

## Live-demo decision tree

| Observed state | Demo action | Required language |
|---|---|---|
| `NORMAL` + `CLEAN` + market open | Analyze one opportunity; submit only with explicit demo authorization | “One unit, limit order, bounded maximum loss, canonical receipt.” |
| `LIQUIDATE_ONLY` | Show reconciliation and containment; do not submit entry | “Untracked or excessive exposure is blocked from compounding.” |
| `UNVERIFIED` | Use sealed replay and cached receipts | “Live dependency failed closed; no cached state is used for risk.” |
| Market closed | Show clock, sealed replay, and evidence | “No forced trade outside the executable window.” |
| No eligible opportunity | Show rejection reasons | “The autonomous decision is no trade.” |
| Lockbox latency exceeds 8 seconds | Stop waiting and use previously cached sanitized receipt | “This receipt was generated before the presentation and is labelled cached.” |

---

## Judge questions — exact answers

### “Did the system make money?”

> “The full Alpaca paper account result is the number shown in the Risk Envelope. Governed closed-trade P&L is shown separately. Today the result is [read the displayed number]. I am not using synthetic replay to answer that question.”

### “Why should we trust paper fills?”

> “Paper trading is execution evidence, not a guarantee of live fill quality. Alpaca documents that paper orders can fill without checking displayed NBBO quantity. That is why CaiSheng caps entries at one contract, uses limit orders, records spread and slippage, and does not present oversized paper fills as scalable alpha.”

### “Was the negative or risky activity your agent?”

> “Only activity with a CaiSheng DecisionRecord, canonical order intent, and broker IDs is claimed as governed agent activity. Any broker exposure without that lineage is labelled untracked and forces LIQUIDATE ONLY.”

### “What did you improve after the incident?”

> “We deleted the direct UI execution engine, fixed signed-quantity reconciliation, excluded terminal historical orders from live-orphan checks, required reconciliation before every new entry, normalized Alpaca enum sides for exact-contract exits, added a broker-authoritative Risk Envelope, and made full-account P&L the headline evidence.”

### “Would you reset the account?”

> “No. I would not reset or replace the competition account to conceal performance. A separate paper account is useful for destructive development tests only, and I would switch the submitted competition account only with written organizer permission.”

### “Where is the AI?”

> “LangGraph coordinates opposing volatility analysts and an independent critic. They interpret evidence and uncertainty. Deterministic code retains authority over prices, EV, maximum loss, quantities, approval, execution, and exits.”

---

## Paper-account and API-key policy

### Recommended account arrangement

1. Keep the current organizer-recognized competition account and its ledger binding unchanged.
2. Create one separate **development/adversarial paper account** for intentionally destructive tests, fault injection, and UI experiments.
3. Generate a new key pair for that new paper account. Never reuse competition credentials in development.
4. Store the development keys only in a separate local environment file that is ignored by Git.
5. Bind every ledger to one immutable Alpaca paper account ID; refuse startup if the credentials resolve to a different account.
6. Do not create or select a new competition account unless the organizers confirm in writing that it is allowed and will remain eligible for judging.

Alpaca's official documentation says each newly created paper account needs new API keys, paper and live credentials/endpoints differ, and new paper accounts are created from the paper-account selector in the dashboard. See [Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading) and [Authentication](https://docs.alpaca.markets/us/v1.1/docs/authentication-1).

### Do I need to give Codex a new API?

No. Codex does not need a personal account or ownership of an API. CaiSheng needs credentials for the paper account being tested. You create and control the account and keys; credentials stay in the local environment and must never be pasted into chat, committed, logged, or rendered in the UI.

---

## Final go/no-go checklist

The demo is ready only when every item is true:

- [ ] Full account P&L is visible and agrees with Alpaca equity minus `$100,000`.
- [ ] Governed P&L is separately labelled.
- [ ] Risk Envelope state agrees with reconciliation.
- [ ] No `.submit_order(` call exists outside `src/volagent/execution/alpaca.py`.
- [ ] All execution, lockbox, broker-risk, evidence, cockpit, lifecycle, and full-suite tests pass.
- [ ] No credentials, account IDs, or raw broker payloads are visible.
- [ ] Sealed replay is clearly labelled non-competition evidence.
- [ ] No entry is submitted under `LIQUIDATE_ONLY`, `UNVERIFIED`, `HALTED`, stale data, or a closed market.
- [ ] A 60-second fallback has been rehearsed twice.
- [ ] The presenter can state the displayed P&L without excuses or ambiguity.

Passing this checklist makes the submission presentation-ready and technically defensible. It cannot guarantee a `10/10` P&L score; only actual broker-confirmed competition performance can do that.
