"""Unit tests for option quote filters and future-quote rejection."""

from datetime import date, datetime, timedelta, timezone
from volagent.config import ContractFiltersConfig
from volagent.domain.enums import DataMode
from volagent.domain.market import OptionContractSnapshot
from volagent.provenance import Provenance
from volagent.quant.quote_filters import filter_option_chain


def test_future_underlying_option_and_evidence_timestamps_rejected():
    """Verify that quotes with future timestamps relative to decision_time are rejected."""
    as_of = datetime(2024, 8, 28, 19, 45, 0, tzinfo=timezone.utc)
    future_time = datetime(2024, 8, 28, 20, 0, 0, tzinfo=timezone.utc)
    exp = date(2024, 9, 6)

    prov = Provenance(
        source_name="test",
        source_uri="test",
        retrieved_at=as_of,
        observed_at=as_of,
        content_hash="h1",
        data_mode=DataMode.REPLAY_SYNTHETIC,
    )

    valid_quote = OptionContractSnapshot(
        symbol="NVDA240906C00125000",
        underlying_symbol="NVDA",
        option_type="call",
        strike=125.0,
        expiration=exp,
        bid=4.80,
        ask=5.00,
        quote_time=as_of,
        volume=1000,
        open_interest=5000,
        provenance=prov,
    )

    future_quote = OptionContractSnapshot(
        symbol="NVDA240906C00130000",
        underlying_symbol="NVDA",
        option_type="call",
        strike=130.0,
        expiration=exp,
        bid=2.80,
        ask=3.00,
        quote_time=future_time,  # In the future!
        volume=1000,
        open_interest=5000,
        provenance=prov,
    )

    cfg = ContractFiltersConfig()
    passed, audit = filter_option_chain([valid_quote, future_quote], "NVDA", exp, as_of, cfg)

    assert len(passed) == 1
    assert passed[0].strike == 125.0
    assert audit["rejection_counts"]["future_timestamp"] == 1


def test_subsecond_endpoint_skew_is_accepted_but_not_time_leakage():
    as_of = datetime(2024, 8, 28, 19, 45, tzinfo=timezone.utc)
    prov = Provenance(source_name="test", source_uri="test", retrieved_at=as_of, observed_at=as_of, content_hash="h2", data_mode=DataMode.REPLAY_SYNTHETIC)
    quote = OptionContractSnapshot(
        symbol="NVDA240906C00125000", underlying_symbol="NVDA", option_type="call", strike=125.0,
        expiration=date(2024, 9, 6), bid=4.80, ask=5.00, quote_time=as_of + timedelta(milliseconds=500),
        volume=1000, open_interest=5000, provenance=prov,
    )
    passed, audit = filter_option_chain([quote], "NVDA", quote.expiration, as_of, ContractFiltersConfig())
    assert passed == [quote]
    assert audit["rejection_counts"]["future_timestamp"] == 0
