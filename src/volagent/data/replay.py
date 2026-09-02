"""File-backed replay scenario loader and dataset manager with sealed outcome support."""

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from volagent.domain.enums import DataMode, EventTiming, OptionType
from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.errors import DataUnavailableError
from volagent.provenance import Provenance
from volagent.quant.pricing import bsm_price

from volagent.config import PROJECT_ROOT
REPLAY_DIR = PROJECT_ROOT / "data" / "replay"


class ReplayDataManager:
    """Manages frozen point-in-time market, option, and evidence replay scenarios loaded from file artifacts."""

    def __init__(self, data_dir: Path | str = REPLAY_DIR):
        self.data_dir = Path(data_dir)

    def get_featured_scenarios(self) -> list[dict[str, Any]]:
        """Return list of available scenario archetypes from manifest."""
        manifest_file = self.data_dir / "manifest.json"
        if not manifest_file.exists():
            return []

        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
        except Exception:
            return []

        scenarios = []
        for s in manifest.get("scenarios", []):
            scenarios.append({
                "scenario_id": s["scenario_id"],
                "symbol": s["symbol"],
                "name": s.get("description", s["scenario_id"]),
                "mode": DataMode.REPLAY_SYNTHETIC,
            })
        return scenarios

    def load_scenario(self, scenario_id: str) -> dict[str, Any]:
        """Load scenario snapshot, option chain, and evidence items from file."""
        manifest_file = self.data_dir / "manifest.json"
        if not manifest_file.exists():
            raise DataUnavailableError(f"Replay manifest not found at {manifest_file}.")

        with open(manifest_file, "r") as f:
            manifest = json.load(f)

        target = None
        for s in manifest.get("scenarios", []):
            if s["scenario_id"] == scenario_id or s["symbol"] == scenario_id.replace("SCENARIO-", ""):
                target = s
                break

        if not target:
            raise DataUnavailableError(f"Scenario '{scenario_id}' is not in the replay dataset.")

        scenario_path = self.data_dir / target["file"]
        if not scenario_path.exists():
            raise DataUnavailableError(f"Scenario file not found: {scenario_path}")

        raw_bytes = scenario_path.read_bytes()
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        data = json.loads(raw_bytes.decode("utf-8"))

        # Verify expected checksum if declared in manifest
        expected_hash = target.get("sha256")
        if expected_hash and file_hash != expected_hash:
            raise DataUnavailableError(f"Scenario file checksum mismatch for {target['file']}: {file_hash} != {expected_hash}")

        inputs = data["decision_inputs"]
        sealed_outcomes = data.get("sealed_outcomes", {})
        u_raw = inputs["underlying"]
        e_raw = inputs["event"]

        if e_raw["symbol"] != u_raw["symbol"]:
            raise DataUnavailableError(
                f"Scenario symbol mismatch: underlying={u_raw['symbol']} event={e_raw['symbol']}."
            )

        dec_dt = datetime.fromisoformat(e_raw["decision_time"]).astimezone(timezone.utc)
        event_dt = datetime.fromisoformat(e_raw["event_time"]).astimezone(timezone.utc)
        exit_dt = datetime.fromisoformat(e_raw["exit_time"]).astimezone(timezone.utc)

        prov = Provenance(
            source_name=f"File Artifact ({target['file']})",
            source_uri=f"file://{scenario_path}",
            retrieved_at=datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc),  # Frozen retrieval time
            observed_at=dec_dt,
            content_hash=file_hash,
            data_mode=DataMode.REPLAY_SYNTHETIC,
        )

        underlying = UnderlyingSnapshot(
            symbol=u_raw["symbol"],
            price=u_raw["price"],
            bid=u_raw["bid"],
            ask=u_raw["ask"],
            quote_time=datetime.fromisoformat(u_raw["quote_time"]).astimezone(timezone.utc),
            previous_close=u_raw["previous_close"],
            realized_vol_10d=u_raw["realized_vol_10d"],
            realized_vol_30d=u_raw["realized_vol_30d"],
            provenance=prov,
        )

        event = EarningsEvent(
            event_id=e_raw["event_id"],
            symbol=e_raw["symbol"],
            event_type=e_raw.get("event_type", "earnings"),
            fiscal_period=e_raw.get("fiscal_period") or e_raw.get("fiscal_quarter", "Q2"),
            event_time=event_dt,
            timing=EventTiming(e_raw["timing"]),
            confirmed=e_raw["confirmed"],
            decision_time=dec_dt,
            exit_time=exit_dt,
            provenance=prov,
        )

        evidence_items = []
        for ev in inputs.get("evidence", []):
            if "observed_at" not in ev:
                raise DataUnavailableError(f"Evidence item {ev.get('evidence_id', '<unknown>')} is missing observed_at.")
            obs_dt = datetime.fromisoformat(ev["observed_at"]).astimezone(timezone.utc)
            evidence_items.append(
                EvidenceItem(
                    evidence_id=ev["evidence_id"],
                    category=ev.get("category") or ev.get("source_type", "filing"),
                    claim=ev.get("claim") or ev.get("summary", ""),
                    magnitude_relevance=ev.get("magnitude_relevance") or ev.get("metric_name", ""),
                    numeric_value=ev.get("numeric_value"),
                    units=ev.get("units"),
                    confidence=ev.get("confidence", 0.8),
                    observed_at=obs_dt,
                    provenance=prov,
                )
            )

        # Build or deserialize option chain
        option_chain = []
        if "option_chain" in inputs and inputs["option_chain"]:
            for opt in inputs["option_chain"]:
                option_underlying = opt.get("underlying_symbol", u_raw["symbol"])
                if option_underlying != u_raw["symbol"]:
                    raise DataUnavailableError(
                        f"Option {opt['symbol']} underlying {option_underlying} does not match {u_raw['symbol']}."
                    )
                exp_d = date.fromisoformat(opt["expiration"]) if isinstance(opt["expiration"], str) else opt["expiration"]
                q_dt = datetime.fromisoformat(opt["quote_time"]).astimezone(timezone.utc) if isinstance(opt["quote_time"], str) else opt["quote_time"]
                option_chain.append(
                    OptionContractSnapshot(
                        symbol=opt["symbol"],
                        underlying_symbol=option_underlying,
                        option_type=OptionType(opt["option_type"].lower()),
                        strike=float(opt["strike"]),
                        expiration=exp_d,
                        bid=float(opt["bid"]),
                        ask=float(opt["ask"]),
                        bid_size=int(opt.get("bid_size", 50)),
                        ask_size=int(opt.get("ask_size", 50)),
                        volume=int(opt.get("volume", 100)),
                        open_interest=int(opt.get("open_interest", 500)),
                        quote_time=q_dt,
                        vendor_implied_vol=float(opt.get("vendor_implied_vol", 0.65)),
                        provenance=prov,
                    )
                )
        else:
            raise DataUnavailableError(f"Scenario {target['scenario_id']} has no point-in-time option_chain artifact.")

        return {
            "scenario_id": target["scenario_id"],
            "underlying": underlying,
            "event": event,
            "option_chain": option_chain,
            "evidence": evidence_items,
            "evidence_items": evidence_items,
            "historical_moves": inputs.get("historical_moves", []),
            "execution_assumptions": inputs.get("execution_assumptions", {"fee_per_contract": 0.65, "slippage_per_contract": 0.02, "multiplier": 100}),
            "sealed_outcomes": sealed_outcomes,
            "provenance": prov,
            "file_hash": file_hash,
            "artifact_hash": file_hash,
        }

    def _build_synthetic_option_chain(
        self,
        symbol: str,
        spot: float,
        as_of: datetime,
        provenance: Provenance,
        is_stale: bool = False,
    ) -> list[OptionContractSnapshot]:
        """Generate high-density synthetic option chain around ATM strike."""
        strikes = [
            round(spot * 0.90, 1),  # Lower Wing
            round(spot * 0.95, 1),
            round(spot * 1.00, 1),  # ATM
            round(spot * 1.05, 1),
            round(spot * 1.10, 1),  # Upper Wing
        ]

        exp_date = date(2024, 8, 30) if symbol == "NVDA" else (date(2024, 10, 25) if symbol == "TSLA" else date(2024, 11, 1))

        # If stale scenario, make quotes 2 hours old
        q_time = as_of if not is_stale else datetime(2024, 10, 31, 18, 0, 0, tzinfo=timezone.utc)
        t_exp = max(2.0 / 365.0, (exp_date - as_of.date()).days / 365.0)
        event_iv = 1.35 if symbol in ("NVDA", "TSLA") else 0.65
        contracts = []
        for k in strikes:
            base_call_px = bsm_price(spot=spot, strike=k, time_to_expiry=t_exp, volatility=event_iv, option_type=OptionType.CALL)
            base_put_px = bsm_price(spot=spot, strike=k, time_to_expiry=t_exp, volatility=event_iv, option_type=OptionType.PUT)

            # Ensure minimum tick of $0.10
            base_call_px = max(0.10, base_call_px)
            base_put_px = max(0.10, base_put_px)

            # Call
            c_bid = round(base_call_px * 0.96, 2)
            c_ask = round(base_call_px * 1.04, 2)
            c_sym = f"{symbol}{exp_date.strftime('%y%m%d')}C{int(k*1000):08d}"
            contracts.append(
                OptionContractSnapshot(
                    symbol=c_sym,
                    underlying_symbol=symbol,
                    option_type="call",
                    strike=k,
                    expiration=exp_date,
                    bid=c_bid,
                    ask=c_ask,
                    bid_size=50,
                    ask_size=50,
                    volume=150,
                    open_interest=500,
                    quote_time=q_time,
                    vendor_implied_vol=0.65,
                    provenance=provenance,
                )
            )

            # Put
            p_bid = round(base_put_px * 0.96, 2)
            p_ask = round(base_put_px * 1.04, 2)
            p_sym = f"{symbol}{exp_date.strftime('%y%m%d')}P{int(k*1000):08d}"
            contracts.append(
                OptionContractSnapshot(
                    symbol=p_sym,
                    underlying_symbol=symbol,
                    option_type="put",
                    strike=k,
                    expiration=exp_date,
                    bid=p_bid,
                    ask=p_ask,
                    bid_size=50,
                    ask_size=50,
                    volume=150,
                    open_interest=500,
                    quote_time=q_time,
                    vendor_implied_vol=0.65,
                    provenance=provenance,
                )
            )

        return contracts
