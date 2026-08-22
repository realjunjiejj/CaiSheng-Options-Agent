"""File-backed replay scenario loader and dataset manager."""

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from volagent.domain.enums import DataMode, EventTiming
from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.errors import DataUnavailableError
from volagent.provenance import Provenance

# Project root is 4 levels up: src/volagent/data/replay.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
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

        with open(manifest_file, "r") as f:
            manifest = json.load(f)

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

        inputs = data["decision_inputs"]
        u_raw = inputs["underlying"]
        e_raw = inputs["event"]

        dec_dt = datetime.fromisoformat(e_raw["decision_time"]).replace(tzinfo=timezone.utc)
        event_dt = datetime.fromisoformat(e_raw["event_time"]).replace(tzinfo=timezone.utc)
        exit_dt = datetime.fromisoformat(e_raw["exit_time"]).replace(tzinfo=timezone.utc)

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
            quote_time=datetime.fromisoformat(u_raw["quote_time"]).replace(tzinfo=timezone.utc),
            previous_close=u_raw["previous_close"],
            realized_vol_10d=u_raw["realized_vol_10d"],
            realized_vol_30d=u_raw["realized_vol_30d"],
            provenance=prov,
        )

        event = EarningsEvent(
            event_id=e_raw["event_id"],
            symbol=e_raw["symbol"],
            fiscal_period=e_raw["fiscal_period"],
            event_time=event_dt,
            timing=EventTiming(e_raw["timing"]),
            confirmed=e_raw["confirmed"],
            decision_time=dec_dt,
            exit_time=exit_dt,
            provenance=prov,
        )

        chain = []
        symbol = underlying.symbol
        spot = underlying.price
        exp_date = date(2024, 9, 6) if symbol == "NVDA" else (date(2024, 11, 1) if symbol == "TSLA" else date(2024, 11, 8))

        if symbol == "NVDA":
            strikes = [115.0, 120.0, 125.0, 130.0, 135.0]
            for k in strikes:
                chain.append(
                    OptionContractSnapshot(
                        symbol=f"NVDA240906C00{int(k*1000):06d}",
                        underlying_symbol="NVDA",
                        option_type="call",
                        strike=k,
                        expiration=exp_date,
                        bid=max(0.20, 4.85 - (k - 125.0)*0.45),
                        ask=max(0.25, 4.95 - (k - 125.0)*0.45),
                        last=4.90,
                        quote_time=dec_dt,
                        volume=5500,
                        open_interest=18500,
                        vendor_implied_vol=0.62,
                        vendor_delta=0.52 if k == 125.0 else 0.30,
                        provenance=prov,
                    )
                )
                chain.append(
                    OptionContractSnapshot(
                        symbol=f"NVDA240906P00{int(k*1000):06d}",
                        underlying_symbol="NVDA",
                        option_type="put",
                        strike=k,
                        expiration=exp_date,
                        bid=max(0.20, 4.85 + (k - 125.0)*0.45),
                        ask=max(0.25, 4.95 + (k - 125.0)*0.45),
                        last=4.90,
                        quote_time=dec_dt,
                        volume=6100,
                        open_interest=19200,
                        vendor_implied_vol=0.62,
                        vendor_delta=-0.48 if k == 125.0 else -0.70,
                        provenance=prov,
                    )
                )
        elif symbol == "TSLA":
            strikes = [190.0, 200.0, 215.0, 230.0, 240.0]
            for k in strikes:
                chain.append(
                    OptionContractSnapshot(
                        symbol=f"TSLA241101C00{int(k*1000):06d}",
                        underlying_symbol="TSLA",
                        option_type="call",
                        strike=k,
                        expiration=exp_date,
                        bid=max(0.30, 11.20 - (k - 215.0)*0.5),
                        ask=max(0.35, 11.50 - (k - 215.0)*0.5),
                        last=11.35,
                        quote_time=dec_dt,
                        volume=4200,
                        open_interest=12500,
                        vendor_implied_vol=0.88,
                        vendor_delta=0.51 if k == 215.0 else 0.22,
                        provenance=prov,
                    )
                )
                chain.append(
                    OptionContractSnapshot(
                        symbol=f"TSLA241101P00{int(k*1000):06d}",
                        underlying_symbol="TSLA",
                        option_type="put",
                        strike=k,
                        expiration=exp_date,
                        bid=max(0.30, 10.40 + (k - 215.0)*0.5),
                        ask=max(0.35, 10.70 + (k - 215.0)*0.5),
                        last=10.55,
                        quote_time=dec_dt,
                        volume=3900,
                        open_interest=11800,
                        vendor_implied_vol=0.88,
                        vendor_delta=-0.49 if k == 215.0 else -0.78,
                        provenance=prov,
                    )
                )
        else:  # AAPL Stale
            chain.append(
                OptionContractSnapshot(
                    symbol="AAPL241108C00225000",
                    underlying_symbol="AAPL",
                    option_type="call",
                    strike=225.0,
                    expiration=exp_date,
                    bid=4.20,
                    ask=4.30,
                    quote_time=datetime(2024, 10, 31, 18, 0, 0, tzinfo=timezone.utc),  # Stale!
                    volume=5000,
                    open_interest=15000,
                    vendor_implied_vol=0.35,
                    vendor_delta=0.52,
                    provenance=prov,
                )
            )
            chain.append(
                OptionContractSnapshot(
                    symbol="AAPL241108P00225000",
                    underlying_symbol="AAPL",
                    option_type="put",
                    strike=225.0,
                    expiration=exp_date,
                    bid=4.10,
                    ask=4.20,
                    quote_time=datetime(2024, 10, 31, 18, 0, 0, tzinfo=timezone.utc),  # Stale!
                    volume=4800,
                    open_interest=14200,
                    vendor_implied_vol=0.35,
                    vendor_delta=-0.48,
                    provenance=prov,
                )
            )

        evidence = [
            EvidenceItem(
                evidence_id=ev["evidence_id"],
                category=ev["category"],
                claim=ev["claim"],
                magnitude_relevance=ev["magnitude_relevance"],
                numeric_value=ev["numeric_value"],
                units=ev["units"],
                confidence=ev["confidence"],
                provenance=prov,
            )
            for ev in inputs.get("evidence", [])
        ]

        return {
            "underlying": underlying,
            "event": event,
            "option_chain": chain,
            "evidence": evidence,
            "historical_moves": inputs.get("historical_moves", []),
            "artifact_hash": file_hash,
        }
