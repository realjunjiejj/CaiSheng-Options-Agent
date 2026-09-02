"""Point-in-time locked shadow benchmarks for competition evidence.

This module deliberately keeps counterfactual economics separate from broker-confirmed
competition P&L.  An intent is sealed before its outcome exists, then every policy is
settled from the same later executable quote snapshot.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import math
import random
import re
from statistics import mean, median
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from volagent.domain.enums import Decision
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.strategies import StrategyCandidate
from volagent.errors import ValidationError


POLICY_IDS = (
    "B0_NO_TRADE",
    "B1_BUY_AND_HOLD_UNDERLYING",
    "B2_ALWAYS_LONG_STRADDLE",
    "B3_ALWAYS_SHORT_DEFINED_RISK_VOL",
    "B4_IMPLIED_MOVE_ONLY",
    "B5_CAISHENG_NO_RESIDUAL",
    "FULL_CAISHENG",
)


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_quote(bid: float, ask: float, label: str) -> None:
    if not math.isfinite(bid) or not math.isfinite(ask):
        raise ValidationError(f"{label} quote must be finite")
    if bid < 0 or ask <= 0:
        raise ValidationError(f"{label} quote must be non-negative with positive ask")
    if bid > ask:
        raise ValidationError(f"{label} quote is crossed")


class BenchmarkOptionQuote(BaseModel):
    """Executable bid/ask for one exact contract at one observation time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_symbol: str
    bid: float
    ask: float
    quote_time: datetime

    @model_validator(mode="after")
    def validate_quote(self) -> "BenchmarkOptionQuote":
        _valid_quote(self.bid, self.ask, self.contract_symbol)
        return self


class BenchmarkLegIntent(BaseModel):
    """Exact contract and executable entry side frozen before the outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_symbol: str
    side: Literal["buy", "sell"]
    ratio_qty: int = Field(ge=1)
    multiplier: int = Field(default=100, gt=0)
    entry_bid: float
    entry_ask: float
    entry_price: float
    quote_time: datetime


class BenchmarkVariantIntent(BaseModel):
    """One sealed policy decision under the common opportunity contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    label: str
    decision: str
    eligible: bool
    quantity: int = Field(ge=0)
    max_loss: float = Field(ge=0.0)
    legs: tuple[BenchmarkLegIntent, ...] = ()
    underlying_shares: int = Field(default=0, ge=0)
    underlying_entry_bid: float | None = None
    underlying_entry_ask: float | None = None
    reason: str = ""


class LockedBenchmarkIntent(BaseModel):
    """Immutable, pre-outcome comparison receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "caisheng.benchmark_intent.v1"
    intent_id: str
    opportunity_id: str
    decision_id: str
    symbol: str
    decision_time: datetime
    exit_time: datetime
    data_mode: str
    starting_nav: float = Field(gt=0.0)
    risk_budget: float = Field(gt=0.0)
    fee_per_contract: float = Field(ge=0.0)
    slippage_per_contract: float = Field(ge=0.0)
    entry_snapshot_hash: str
    evidence_tier: Literal["shadow_counterfactual"] = "shadow_counterfactual"
    competition_pnl_eligible: Literal[False] = False
    outcome_known: Literal[False] = False
    variants: tuple[BenchmarkVariantIntent, ...]
    receipt_hash: str

    def compute_hash(self) -> str:
        return _canonical_hash(self.model_dump(mode="json", exclude={"receipt_hash"}))

    def variant(self, policy_id: str) -> BenchmarkVariantIntent:
        for variant in self.variants:
            if variant.policy_id == policy_id:
                return variant
        raise KeyError(policy_id)


class BenchmarkExitSnapshot(BaseModel):
    """One common exit snapshot used to settle every locked policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "caisheng.benchmark_exit_snapshot.v1"
    observed_at: datetime
    underlying_bid: float
    underlying_ask: float
    underlying_quote_time: datetime
    option_quotes: tuple[BenchmarkOptionQuote, ...]
    snapshot_hash: str

    @model_validator(mode="after")
    def validate_snapshot(self) -> "BenchmarkExitSnapshot":
        _valid_quote(self.underlying_bid, self.underlying_ask, "underlying exit")
        if self.underlying_quote_time > self.observed_at:
            raise ValidationError("underlying exit quote timestamp is after snapshot observation time")
        symbols = [quote.contract_symbol for quote in self.option_quotes]
        if len(symbols) != len(set(symbols)):
            raise ValidationError("exit snapshot contains duplicate contract symbols")
        if any(quote.quote_time > self.observed_at for quote in self.option_quotes):
            raise ValidationError("exit quote timestamp is after snapshot observation time")
        return self

    def compute_hash(self) -> str:
        return _canonical_hash(self.model_dump(mode="json", exclude={"snapshot_hash"}))

    @classmethod
    def create_and_hash(cls, **kwargs: object) -> "BenchmarkExitSnapshot":
        kwargs.pop("snapshot_hash", None)
        draft = cls(snapshot_hash="", **kwargs)
        return draft.model_copy(update={"snapshot_hash": draft.compute_hash()})


class BenchmarkVariantOutcome(BaseModel):
    """Settled economics for one locked policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    label: str
    decision: str
    executable: bool
    quantity: int = Field(ge=0)
    gross_pnl: float
    costs: float = Field(ge=0.0)
    net_pnl: float
    max_loss: float = Field(ge=0.0)
    return_on_risk: float
    reason: str = ""


class SettledBenchmarkReceipt(BaseModel):
    """Post-outcome receipt linked to a sealed intent and common exit snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "caisheng.benchmark_outcome.v1"
    outcome_id: str
    intent_id: str
    opportunity_id: str
    decision_id: str
    symbol: str
    data_mode: str
    settled_at: datetime
    exit_snapshot_hash: str
    evidence_tier: Literal["shadow_counterfactual"] = "shadow_counterfactual"
    competition_pnl_eligible: Literal[False] = False
    outcomes: tuple[BenchmarkVariantOutcome, ...]
    receipt_hash: str

    def compute_hash(self) -> str:
        return _canonical_hash(self.model_dump(mode="json", exclude={"receipt_hash"}))

    def outcome(self, policy_id: str) -> BenchmarkVariantOutcome:
        for outcome in self.outcomes:
            if outcome.policy_id == policy_id:
                return outcome
        raise KeyError(policy_id)


def _candidate_variant(
    *,
    policy_id: str,
    label: str,
    candidate: StrategyCandidate | None,
    chain: dict[str, OptionContractSnapshot],
    risk_budget: float,
) -> BenchmarkVariantIntent:
    if candidate is None:
        return BenchmarkVariantIntent(
            policy_id=policy_id,
            label=label,
            decision="no_trade",
            eligible=False,
            quantity=0,
            max_loss=0.0,
            reason="Required strategy candidate was unavailable at lock time.",
        )
    if candidate.quantity <= 0 or candidate.max_loss <= 0 or candidate.max_loss > risk_budget:
        return BenchmarkVariantIntent(
            policy_id=policy_id,
            label=label,
            decision="no_trade",
            eligible=False,
            quantity=0,
            max_loss=max(0.0, candidate.max_loss),
            reason="Candidate did not fit the common risk budget.",
        )

    legs: list[BenchmarkLegIntent] = []
    for leg in candidate.legs:
        quote = chain.get(leg.contract_symbol)
        if quote is None:
            raise ValidationError(f"missing locked entry quote for {leg.contract_symbol}")
        _valid_quote(quote.bid, quote.ask, quote.symbol)
        entry_price = quote.ask if leg.side == "buy" else quote.bid
        legs.append(
            BenchmarkLegIntent(
                contract_symbol=quote.symbol,
                side=leg.side,
                ratio_qty=leg.ratio_qty,
                multiplier=quote.multiplier,
                entry_bid=quote.bid,
                entry_ask=quote.ask,
                entry_price=entry_price,
                quote_time=quote.quote_time,
            )
        )
    return BenchmarkVariantIntent(
        policy_id=policy_id,
        label=label,
        decision=candidate.decision.value,
        eligible=True,
        quantity=candidate.quantity,
        max_loss=candidate.max_loss,
        legs=tuple(legs),
    )


def lock_benchmark_intent(
    *,
    opportunity_id: str,
    decision_id: str,
    decision_time: datetime,
    exit_time: datetime,
    underlying: UnderlyingSnapshot,
    option_chain: Sequence[OptionContractSnapshot],
    candidates: Sequence[StrategyCandidate],
    approved_candidate: StrategyCandidate | None,
    final_decision: Decision,
    starting_nav: float,
    risk_budget: float,
    fee_per_contract: float,
    slippage_per_contract: float,
    data_mode: str = "live",
) -> LockedBenchmarkIntent:
    """Seal all benchmark decisions and executable entry quotes before outcome."""
    if exit_time <= decision_time:
        raise ValidationError("benchmark exit time must be after decision time")
    if underlying.bid is None or underlying.ask is None:
        raise ValidationError("underlying benchmark requires bid and ask")
    _valid_quote(underlying.bid, underlying.ask, "underlying entry")
    if underlying.quote_time > decision_time:
        raise ValidationError("underlying quote is after benchmark decision time")
    if data_mode == "live" and decision_time - underlying.quote_time > timedelta(minutes=10):
        raise ValidationError("stale underlying entry quote")
    if starting_nav <= 0 or risk_budget <= 0:
        raise ValidationError("starting NAV and risk budget must be positive")

    chain = {quote.symbol: quote for quote in option_chain}
    if len(chain) != len(option_chain):
        raise ValidationError("option chain contains duplicate contract symbols")
    if any(quote.quote_time > decision_time for quote in option_chain):
        raise ValidationError("option entry quote is after benchmark decision time")
    if data_mode == "live" and any(
        decision_time - quote.quote_time > timedelta(minutes=10) for quote in option_chain
    ):
        raise ValidationError("stale option entry quote")

    by_decision = {candidate.decision: candidate for candidate in candidates}
    straddle = by_decision.get(Decision.LONG_STRADDLE)
    short_defined = by_decision.get(Decision.SHORT_IRON_BUTTERFLY)
    shares = int(risk_budget // underlying.ask)
    underlying_variant = BenchmarkVariantIntent(
        policy_id="B1_BUY_AND_HOLD_UNDERLYING",
        label="Buy & hold underlying",
        decision="buy_underlying" if shares else "no_trade",
        eligible=shares > 0,
        quantity=shares,
        max_loss=round(shares * underlying.ask, 8),
        underlying_shares=shares,
        underlying_entry_bid=underlying.bid,
        underlying_entry_ask=underlying.ask,
        reason="Capital-matched to the common risk budget." if shares else "Risk budget cannot buy one share.",
    )
    no_trade = BenchmarkVariantIntent(
        policy_id="B0_NO_TRADE",
        label="No trade",
        decision="no_trade",
        eligible=True,
        quantity=0,
        max_loss=0.0,
        reason="Cash control.",
    )
    implied = BenchmarkVariantIntent(
        policy_id="B4_IMPLIED_MOVE_ONLY",
        label="Implied-move-only policy",
        decision="no_trade",
        eligible=True,
        quantity=0,
        max_loss=0.0,
        reason="The market-implied anchor alone supplies no residual executable edge.",
    )
    no_residual = BenchmarkVariantIntent(
        policy_id="B5_CAISHENG_NO_RESIDUAL",
        label="CaiSheng without residual correction",
        decision="no_trade",
        eligible=True,
        quantity=0,
        max_loss=0.0,
        reason="Lambda=0 leaves the implied-move anchor and no positive residual edge.",
    )

    long_variant = _candidate_variant(
        policy_id="B2_ALWAYS_LONG_STRADDLE",
        label="Always long straddle",
        candidate=straddle,
        chain=chain,
        risk_budget=risk_budget,
    )
    short_variant = _candidate_variant(
        policy_id="B3_ALWAYS_SHORT_DEFINED_RISK_VOL",
        label="Always short defined-risk volatility",
        candidate=short_defined,
        chain=chain,
        risk_budget=risk_budget,
    )
    if final_decision == Decision.NO_TRADE or approved_candidate is None:
        full_variant = BenchmarkVariantIntent(
            policy_id="FULL_CAISHENG",
            label="Full CaiSheng",
            decision="no_trade",
            eligible=True,
            quantity=0,
            max_loss=0.0,
            reason="Full agent abstained after its evidence and risk gates.",
        )
    else:
        full_variant = _candidate_variant(
            policy_id="FULL_CAISHENG",
            label="Full CaiSheng",
            candidate=approved_candidate,
            chain=chain,
            risk_budget=risk_budget,
        )

    variants = (no_trade, underlying_variant, long_variant, short_variant, implied, no_residual, full_variant)
    entry_payload = {
        "underlying": underlying.model_dump(mode="json"),
        "options": [chain[symbol].model_dump(mode="json") for symbol in sorted(chain)],
    }
    entry_snapshot_hash = _canonical_hash(entry_payload)
    identity = _canonical_hash(
        {
            "opportunity_id": opportunity_id,
            "decision_id": decision_id,
            "decision_time": decision_time.isoformat(),
            "entry_snapshot_hash": entry_snapshot_hash,
        }
    )
    draft = LockedBenchmarkIntent(
        intent_id=f"bench-{identity[:24]}",
        opportunity_id=opportunity_id,
        decision_id=decision_id,
        symbol=underlying.symbol,
        decision_time=decision_time,
        exit_time=exit_time,
        data_mode=data_mode,
        starting_nav=starting_nav,
        risk_budget=risk_budget,
        fee_per_contract=fee_per_contract,
        slippage_per_contract=slippage_per_contract,
        entry_snapshot_hash=entry_snapshot_hash,
        variants=variants,
        receipt_hash="",
    )
    return draft.model_copy(update={"receipt_hash": draft.compute_hash()})


def settle_benchmark_intent(
    intent: LockedBenchmarkIntent,
    exit_snapshot: BenchmarkExitSnapshot,
) -> SettledBenchmarkReceipt:
    """Settle every locked policy against the same executable exit snapshot."""
    if intent.receipt_hash != intent.compute_hash():
        raise ValidationError("locked benchmark intent hash is invalid")
    if exit_snapshot.snapshot_hash != exit_snapshot.compute_hash():
        raise ValidationError("benchmark exit snapshot hash is invalid")
    if exit_snapshot.observed_at < intent.exit_time:
        raise ValidationError("exit snapshot is before locked exit time")
    if exit_snapshot.underlying_quote_time < intent.exit_time:
        raise ValidationError("underlying exit quote predates locked exit time")
    if intent.data_mode == "live" and (
        exit_snapshot.observed_at - exit_snapshot.underlying_quote_time > timedelta(minutes=10)
    ):
        raise ValidationError("underlying exit quote is stale")

    quotes = {quote.contract_symbol: quote for quote in exit_snapshot.option_quotes}
    required_symbols = {
        leg.contract_symbol
        for variant in intent.variants
        if variant.eligible
        for leg in variant.legs
    }
    missing_symbols = sorted(required_symbols - set(quotes))
    if missing_symbols:
        raise ValidationError(f"missing exact exit quotes: {', '.join(missing_symbols)}")
    for symbol in sorted(required_symbols):
        quote = quotes[symbol]
        if quote.quote_time < intent.exit_time:
            raise ValidationError(f"exit quote predates locked exit time: {symbol}")
        if intent.data_mode == "live" and (
            exit_snapshot.observed_at - quote.quote_time > timedelta(minutes=10)
        ):
            raise ValidationError(f"stale exit quote: {symbol}")
    outcomes: list[BenchmarkVariantOutcome] = []
    cost_per_side = intent.fee_per_contract + intent.slippage_per_contract
    for variant in intent.variants:
        gross = 0.0
        costs = 0.0
        executable = variant.eligible
        reason = variant.reason
        if variant.decision == "buy_underlying" and variant.underlying_entry_ask is not None:
            gross = (exit_snapshot.underlying_bid - variant.underlying_entry_ask) * variant.underlying_shares
        elif variant.legs and variant.quantity > 0:
            missing = [leg.contract_symbol for leg in variant.legs if leg.contract_symbol not in quotes]
            if missing:
                executable = False
                reason = f"Missing exit quotes: {', '.join(missing)}"
            else:
                for leg in variant.legs:
                    quote = quotes[leg.contract_symbol]
                    if quote.quote_time > exit_snapshot.observed_at:
                        raise ValidationError(f"future exit quote for {leg.contract_symbol}")
                    units = variant.quantity * leg.ratio_qty * leg.multiplier
                    if leg.side == "buy":
                        gross += (quote.bid - leg.entry_price) * units
                    else:
                        gross += (leg.entry_price - quote.ask) * units
                    costs += variant.quantity * leg.ratio_qty * 2 * cost_per_side
        elif variant.decision == "no_trade":
            executable = variant.eligible

        if not executable:
            gross = 0.0
            costs = 0.0
        net = gross - costs
        outcomes.append(
            BenchmarkVariantOutcome(
                policy_id=variant.policy_id,
                label=variant.label,
                decision=variant.decision,
                executable=executable,
                quantity=variant.quantity if executable else 0,
                gross_pnl=round(gross, 8),
                costs=round(costs, 8),
                net_pnl=round(net, 8),
                max_loss=variant.max_loss,
                return_on_risk=round(net / variant.max_loss, 8) if variant.max_loss > 0 else 0.0,
                reason=reason,
            )
        )

    outcome_id = f"outcome-{_canonical_hash({'intent_id': intent.intent_id, 'exit': exit_snapshot.snapshot_hash})[:24]}"
    draft = SettledBenchmarkReceipt(
        outcome_id=outcome_id,
        intent_id=intent.intent_id,
        opportunity_id=intent.opportunity_id,
        decision_id=intent.decision_id,
        symbol=intent.symbol,
        data_mode=intent.data_mode,
        settled_at=exit_snapshot.observed_at,
        exit_snapshot_hash=exit_snapshot.snapshot_hash,
        outcomes=tuple(outcomes),
        receipt_hash="",
    )
    return draft.model_copy(update={"receipt_hash": draft.compute_hash()})


def _occ_expiration(contract_symbol: str) -> date | None:
    match = re.fullmatch(r"[A-Z]{1,6}(\d{6})[CP]\d{8}", contract_symbol.upper())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%y%m%d").date()
    except ValueError:
        return None


def settle_due_benchmark_intents(
    *,
    ledger: object,
    market_adapter: object,
    now: datetime,
    max_quote_age: timedelta = timedelta(minutes=10),
) -> dict[str, object]:
    """Read-only market settlement of all due, still-pending benchmark intents.

    A due intent remains pending unless every exact contract and the underlying
    have fresh, non-crossed quotes.  Partial evidence is never frozen as an
    outcome, because doing so would make the comparison depend on missing data.
    """
    pending_rows = ledger.list_benchmark_intents(pending_only=True)
    due: list[LockedBenchmarkIntent] = []
    errors: list[str] = []
    for row in pending_rows:
        try:
            intent = LockedBenchmarkIntent.model_validate_json(row["raw_payload"])
            if intent.data_mode == "live" and intent.exit_time <= now:
                due.append(intent)
        except Exception as exc:
            errors.append(f"invalid persisted benchmark intent: {type(exc).__name__}")

    settled = 0
    for intent in due:
        try:
            underlying = market_adapter.get_underlying_snapshot(intent.symbol)
            if underlying is None or underlying.bid is None or underlying.ask is None:
                raise ValidationError("fresh underlying quote unavailable")
            if underlying.quote_time > now or now - underlying.quote_time > max_quote_age:
                raise ValidationError("underlying exit quote is stale or future-dated")

            contract_symbols = {
                leg.contract_symbol
                for variant in intent.variants
                for leg in variant.legs
            }
            expirations = {_occ_expiration(symbol) for symbol in contract_symbols}
            if None in expirations:
                raise ValidationError("locked contract has invalid OCC symbol")
            earliest = min(expirations) if expirations else now.date()
            latest = max(expirations) if expirations else now.date()
            chain = market_adapter.get_option_chain(
                intent.symbol,
                earliest,
                latest,
                None,
            )
            by_symbol = {quote.symbol: quote for quote in chain}
            missing = sorted(contract_symbols - set(by_symbol))
            if missing:
                raise ValidationError(f"exact exit contracts unavailable: {', '.join(missing)}")

            exit_quotes: list[BenchmarkOptionQuote] = []
            for symbol in sorted(contract_symbols):
                quote = by_symbol[symbol]
                if quote.quote_time > now or now - quote.quote_time > max_quote_age:
                    raise ValidationError(f"exit quote is stale or future-dated: {symbol}")
                exit_quotes.append(
                    BenchmarkOptionQuote(
                        contract_symbol=symbol,
                        bid=quote.bid,
                        ask=quote.ask,
                        quote_time=quote.quote_time,
                    )
                )
            exit_snapshot = BenchmarkExitSnapshot.create_and_hash(
                observed_at=now,
                underlying_bid=underlying.bid,
                underlying_ask=underlying.ask,
                underlying_quote_time=underlying.quote_time,
                option_quotes=exit_quotes,
            )
            ledger.record_benchmark_outcome(settle_benchmark_intent(intent, exit_snapshot))
            settled += 1
        except Exception as exc:
            errors.append(f"{intent.intent_id}: {exc}")

    return {
        "due": len(due),
        "settled": settled,
        "pending": len(due) - settled,
        "errors": errors,
    }


def _max_drawdown(values: Sequence[float]) -> float:
    equity = peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _max_consecutive_losses(values: Sequence[float]) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def _paired_interval(values: Sequence[float], *, draws: int = 2000) -> list[float] | None:
    """Deterministic percentile bootstrap interval for the paired mean delta."""
    if len(values) < 2:
        return None
    rng = random.Random(17_031)
    sample_means = [
        mean(rng.choice(values) for _ in values)
        for _ in range(draws)
    ]
    sample_means.sort()
    return [
        round(sample_means[int(0.025 * (draws - 1))], 8),
        round(sample_means[int(0.975 * (draws - 1))], 8),
    ]


def _two_sided_sign_p_value(wins: int, losses: int) -> float | None:
    n = wins + losses
    if n == 0:
        return None
    tail = sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def aggregate_benchmark_receipts(receipts: Sequence[SettledBenchmarkReceipt]) -> dict[str, object]:
    """Build a claim-safe policy comparison from settled paired outcomes."""
    ordered = sorted(receipts, key=lambda receipt: (receipt.settled_at, receipt.intent_id))
    rows: list[dict[str, object]] = []
    for policy_id in POLICY_IDS:
        outcomes = [receipt.outcome(policy_id) for receipt in ordered]
        values = [outcome.net_pnl for outcome in outcomes if outcome.executable]
        traded = [outcome for outcome in outcomes if outcome.executable and outcome.decision != "no_trade"]
        gains = sum(value for value in values if value > 0)
        losses = -sum(value for value in values if value < 0)
        risk = sum(outcome.max_loss for outcome in traded)
        lower_count = max(1, math.ceil(len(values) * 0.05)) if values else 0
        cvar = sum(sorted(values)[:lower_count]) / lower_count if lower_count else 0.0
        net = sum(values)
        paired_full_minus_policy = []
        for receipt in ordered:
            full_outcome = receipt.outcome("FULL_CAISHENG")
            policy_outcome = receipt.outcome(policy_id)
            if full_outcome.executable and policy_outcome.executable:
                paired_full_minus_policy.append(full_outcome.net_pnl - policy_outcome.net_pnl)
        paired_wins = sum(value > 0 for value in paired_full_minus_policy)
        paired_losses = sum(value < 0 for value in paired_full_minus_policy)
        rows.append(
            {
                "policy_id": policy_id,
                "label": outcomes[0].label if outcomes else policy_id,
                "opportunities": len(ordered),
                "trades": len(traded),
                "participation_rate": len(traded) / len(ordered) if ordered else 0.0,
                "net_pnl": round(net, 8),
                "average_pnl": round(sum(values) / len(values), 8) if values else 0.0,
                "median_pnl": round(median(values), 8) if values else 0.0,
                "win_rate": sum(value > 0 for value in values) / len(values) if values else 0.0,
                "profit_factor": round(gains / losses, 8) if losses else None,
                "max_drawdown": round(_max_drawdown(values), 8),
                "return_on_risk": round(net / risk, 8) if risk else 0.0,
                "cvar_95": round(cvar, 8),
                "spread_fees_slippage": round(sum(outcome.costs for outcome in outcomes), 8),
                "worst_trade": round(min(values), 8) if values else 0.0,
                "max_consecutive_losses": _max_consecutive_losses(values),
                "incremental_pnl_vs_full": round(-sum(paired_full_minus_policy), 8) if paired_full_minus_policy else 0.0,
                "full_incremental_pnl": round(sum(paired_full_minus_policy), 8) if paired_full_minus_policy else 0.0,
                "paired_mean_delta_full_minus_policy": round(mean(paired_full_minus_policy), 8) if paired_full_minus_policy else 0.0,
                "paired_mean_delta_95_ci": _paired_interval(paired_full_minus_policy),
                "paired_wins": paired_wins,
                "paired_losses": paired_losses,
                "paired_ties": sum(value == 0 for value in paired_full_minus_policy),
                "paired_sign_test_p_value": _two_sided_sign_p_value(paired_wins, paired_losses),
            }
        )
    return {
        "schema_version": "caisheng.benchmark_aggregate.v1",
        "evidence_tier": "shadow_counterfactual",
        "competition_pnl_eligible": False,
        "claim_boundary": "Locked shadow counterfactuals; never Alpaca competition P&L.",
        "opportunities": len(ordered),
        "policies": rows,
    }
