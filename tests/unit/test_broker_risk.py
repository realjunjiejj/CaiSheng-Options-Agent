"""Behavior tests for the judge-facing, broker-authoritative Risk Envelope."""

from volagent.execution.broker_risk import build_broker_risk_envelope


def test_orphan_broker_positions_force_liquidate_only_and_show_account_truth():
    positions = [
        {
            "symbol": "MSFT260902C00512500",
            "qty": "43",
            "side": "PositionSide.LONG",
            "market_value": "8471.0",
            "unrealized_pl": "-6450.0",
        },
        {
            "symbol": "MSFT260902P00490000",
            "qty": "43",
            "side": "PositionSide.LONG",
            "market_value": "0.0",
            "unrealized_pl": "0.0",
        },
    ]

    envelope = build_broker_risk_envelope(
        positions=positions,
        governed_contract_symbols=set(),
        snapshot_verified=True,
        starting_nav=100_000.0,
        current_equity=88_268.10,
        system_halted=True,
        drawdown_halt_pct=0.01,
        max_contracts=1,
    )

    assert envelope.mode == "LIQUIDATE_ONLY"
    assert envelope.full_account_net_pnl == -11_731.90
    assert envelope.broker_position_legs == 2
    assert envelope.governed_position_legs == 0
    assert envelope.orphan_position_legs == 2
    assert envelope.max_abs_contract_quantity == 43
    assert envelope.gross_marked_exposure == 8_471.0
    assert envelope.unrealized_pnl == -6_450.0
    assert envelope.underlying_symbols == ["MSFT"]
    assert "UNTRACKED_BROKER_EXPOSURE" in envelope.violations
    assert "CONTRACT_QUANTITY_LIMIT" in envelope.violations


def test_clean_governed_position_can_be_normal():
    symbol = "SPY260908C00765000"
    envelope = build_broker_risk_envelope(
        positions=[
            {
                "symbol": symbol,
                "qty": "1",
                "side": "PositionSide.LONG",
                "market_value": "120.0",
                "unrealized_pl": "5.0",
            }
        ],
        governed_contract_symbols={symbol},
        snapshot_verified=True,
        starting_nav=100_000.0,
        current_equity=100_005.0,
        system_halted=False,
        drawdown_halt_pct=0.01,
        max_contracts=1,
    )

    assert envelope.mode == "NORMAL"
    assert envelope.orphan_position_legs == 0
    assert envelope.violations == []


def test_unverified_snapshot_never_claims_normal_mode():
    envelope = build_broker_risk_envelope(
        positions=[],
        governed_contract_symbols=set(),
        snapshot_verified=False,
        starting_nav=100_000.0,
        current_equity=None,
        system_halted=False,
        drawdown_halt_pct=0.01,
        max_contracts=1,
    )

    assert envelope.mode == "UNVERIFIED"
    assert envelope.full_account_net_pnl is None
    assert envelope.violations == ["UNVERIFIED_BROKER_SNAPSHOT"]
