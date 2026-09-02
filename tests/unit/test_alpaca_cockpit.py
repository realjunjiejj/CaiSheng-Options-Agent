"""Unit and adversarial tests for Milestone 5: Alpaca MCP Integration, CLI Proofs & Cockpit."""

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from volagent.cli.preflight import run_cli_preflight
from volagent.cli.reconcile import run_cli_reconciliation
from volagent.config import MandateConfig, VolAgentSettings
from volagent.data.alpaca_mcp import AlpacaMCPService, AlpacaMCPTools
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter, AlpacaPortfolioAdapter
from volagent.domain.enums import BrokerTarget, DataMode, Decision, ExecutionStatus
from volagent.domain.execution import ExecutionReceipt
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.execution.alpaca import AlpacaPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.provenance import Provenance
from volagent.ui.integration_status import (
    PRIMARY_WORKSPACES,
    run_mcp_read_verification,
    sanitize_preflight_for_judges,
)
from volagent.ui.pages.cockpit import build_competition_judge_summary
from volagent.ui.pages.overview import judge_overview_html


def test_alpaca_mcp_tool_schemas():
    """Criterion 1: Alpaca MCP tools provide valid schemas for account, positions, orders, clock, and order submission."""
    acc_tool = AlpacaMCPTools.get_account_tool()
    assert acc_tool["name"] == "alpaca_get_account"

    pos_tool = AlpacaMCPTools.get_positions_tool()
    assert pos_tool["name"] == "alpaca_get_positions"

    clock_tool = AlpacaMCPTools.get_market_clock_tool()
    assert clock_tool["name"] == "alpaca_get_market_clock"

    order_tool = AlpacaMCPTools.submit_multileg_order_tool()
    assert order_tool["name"] == "alpaca_submit_multileg_order"
    assert order_tool["parameters"]["required"] == ["approval_token", "decision_id"]


def test_judge_navigation_has_only_backend_linked_workspaces():
    assert PRIMARY_WORKSPACES == ("Overview", "Agent", "Operations", "Results")


def test_competition_summary_is_decisive_and_never_exposes_account_id(tmp_path):
    settings = VolAgentSettings()
    settings.competition = settings.competition.model_copy(
        update={"enabled": True, "lease_path": str(tmp_path / "missing-arm.json")}
    )
    summary = build_competition_judge_summary(settings, "secret-paper-account-id")

    assert summary["status"] == "DISARMED"
    assert summary["paper_only"] is True
    assert summary["symbols"] == ["SPY", "QQQ", "IWM"]
    assert "secret-paper-account-id" not in str(summary)


def test_results_workspace_is_one_decisive_page_without_nested_tabs():
    app_source = (Path(__file__).parents[2] / "app.py").read_text()

    assert "EVIDENCE_VIEWS" not in app_source
    assert "evidence_tabs = st.tabs" not in app_source
    assert 'if workspace == "Results":\n        render_scoreboard_page()' in app_source


def test_overview_maps_the_strategy_to_alpaca_and_judge_evidence():
    markup = judge_overview_html(
        starting_nav=100_000.0,
        hard_risk_dollars=500.0,
        max_entries_per_day=1,
        symbols=["SPY", "QQQ", "IWM"],
    )

    assert "Trade movement only when the edge survives debate" in markup
    assert "Trading API" in markup
    assert "OrderClass.MLEG" in markup
    assert "FastMCP" in markup
    assert "CLI" in markup
    assert "$500" in markup
    assert "Only broker-confirmed closes count" in markup


def test_judge_ui_never_claims_unverified_connectivity_or_live_replay_execution():
    app_source = (Path(__file__).parents[2] / "app.py").read_text()

    assert "FASTMCP SSE endpoint connected" not in app_source
    assert "Execute via Alpaca API" not in app_source
    assert "render_rough_vol_simulator_page" not in app_source
    assert "workspace = st.radio(" in app_source
    assert "tab_command" not in app_source
    assert 'workflow.run({"symbol": symbol, "ledger": replay_ledger})' in app_source
    assert "caisheng-replay-ui-" in app_source
    assert "Quantitative Risk Gate (Passed)" not in app_source
    assert "Post-Earnings Guidance · High Dispersion" not in app_source
    assert "Execute in Local Simulator" not in app_source
    assert "Approve Plan Token" not in app_source
    assert "CONTROLLED REPLAY" in app_source
    assert "NOT COMPETITION P&amp;L" in app_source
    assert "PUBLIC JUDGE DEMO" not in app_source
    assert "PAPER ARMED" not in app_source
    assert "FAST-MCP V2 LIVE" not in app_source
    assert "TRACK 02" not in app_source
    assert "SHORT VOL ADVOCATE" in app_source


def test_judge_preflight_summary_omits_account_identifier_and_secrets():
    raw = {
        "overall_status": "CLEAN",
        "generated_at": "2026-08-30T01:02:03+00:00",
        "checks": [{"check": "account_accessibility", "status": "PASS"}],
        "account": {
            "account_id": "PAPER-SECRET-ID",
            "equity": 101_250.0,
            "buying_power": 87_500.0,
            "paper_endpoint": True,
            "api_key": "DO-NOT-RENDER",
        },
    }

    summary = sanitize_preflight_for_judges(raw)

    rendered = str(summary)
    assert summary["overall_status"] == "CLEAN"
    assert summary["account"]["equity"] == 101_250.0
    assert "account_id" not in summary["account"]
    assert "PAPER-SECRET-ID" not in rendered
    assert "DO-NOT-RENDER" not in rendered


def test_mcp_read_verification_proves_tools_without_exposing_account_id():
    service = MagicMock()
    service.handle_tool_call.side_effect = [
        {
            "status": "SUCCESS",
            "call_id": "call-account",
            "result": {
                "account_id": "PAPER-SECRET-ID",
                "equity": 100_500.0,
                "buying_power": 150_000.0,
                "as_of_time": "2026-08-30T01:02:03+00:00",
            },
        },
        {
            "status": "SUCCESS",
            "call_id": "call-clock",
            "result": {
                "is_open": False,
                "next_open": "2026-08-31T13:30:00+00:00",
                "next_close": "2026-08-31T20:00:00+00:00",
                "timestamp": "2026-08-30T01:02:03+00:00",
            },
        },
    ]
    service.ledger.list_mcp_audit_events.return_value = [{}, {}]

    proof = run_mcp_read_verification(service)

    assert proof["overall_status"] == "PASS"
    assert proof["tools"]["alpaca_get_account"]["call_id"] == "call-account"
    assert proof["tools"]["alpaca_get_market_clock"]["status"] == "SUCCESS"
    assert proof["audit_event_count"] == 2
    assert proof["account"]["equity"] == 100_500.0
    assert "account_id" not in proof["account"]
    assert "PAPER-SECRET-ID" not in str(proof)


def test_mcp_read_verification_fails_closed_when_one_tool_fails():
    service = MagicMock()
    service.handle_tool_call.side_effect = [
        {"status": "SUCCESS", "call_id": "call-account", "result": {}},
        {"status": "ERROR", "call_id": "call-clock", "error": "unavailable"},
    ]
    service.ledger.list_mcp_audit_events.return_value = [{}, {}]

    proof = run_mcp_read_verification(service)

    assert proof["overall_status"] == "FAIL"
    assert proof["tools"]["alpaca_get_market_clock"]["status"] == "ERROR"


def test_alpaca_mcp_read_tools_and_sanitization(tmp_path):
    """Criterion 1: MCP read tools execute cleanly, redact sensitive arguments in nested lists/dicts, and record audit events."""
    db_file = tmp_path / "mcp_test.db"
    ledger = ExecutionLedger(db_path=db_file)

    # Injected authenticated adapter
    mock_adapter = MagicMock(spec=AlpacaPortfolioAdapter)
    mock_adapter.fetch_portfolio_snapshot.return_value = MagicMock(
        is_stale=False,
        account_id="ACC-PAPER-12345",
        equity=100000.0,
        cash=50000.0,
        buying_power=200000.0,
        total_daily_pl=0.0,
        timestamp=datetime.now(timezone.utc),
    )

    service = AlpacaMCPService(portfolio_adapter=mock_adapter, ledger=ledger)

    # 1. Test account summary with nested lists and dicts
    args_with_secret = {
        "symbol": "NVDA",
        "api_key": "SECRET_KEY_123",
        "nested": {"secret_token": "TOK999"},
        "nested_list": [{"token": "LIST_SECRET_456"}, "normal_string"],
    }
    res = service.handle_tool_call(
        tool_name="alpaca_get_account",
        arguments=args_with_secret,
        decision_id="dec-test-01",
    )

    assert res["status"] == "SUCCESS"
    assert res["result"]["equity"] == 100000.0
    assert res["result"]["account_id"] == "ACC-PAPER-12345"

    # 2. Check audit persistence and deep redaction in lists and dicts
    audit_events = ledger.list_mcp_audit_events()
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["tool_name"] == "alpaca_get_account"
    assert event["decision_id"] == "dec-test-01"
    assert "SECRET_KEY_123" not in event["sanitized_arguments"]
    assert "LIST_SECRET_456" not in event["sanitized_arguments"]
    assert "[REDACTED]" in event["sanitized_arguments"]

    quote = SimpleNamespace(
        price=125.0, bid=124.99, ask=125.01, quote_time=datetime.now(timezone.utc)
    )
    contract = SimpleNamespace(quote_time=datetime.now(timezone.utc))
    with (
        patch.object(AlpacaLiveMarketAdapter, "get_underlying_snapshot", return_value=quote),
        patch.object(AlpacaLiveMarketAdapter, "get_option_chain", return_value=[contract]),
    ):
        quote_result = service.handle_tool_call("alpaca_get_quote", {"symbol": "NVDA"})
        chain_result = service.handle_tool_call(
            "alpaca_get_option_chain", {"symbol": "NVDA", "target_dte": 7}
        )
    assert quote_result["status"] == "SUCCESS"
    assert quote_result["result"]["spot"] == 125.0
    assert chain_result["status"] == "SUCCESS"
    assert chain_result["result"]["contracts_count"] == 1


def test_alpaca_mcp_write_tool_blocked_by_kill_switch(tmp_path):
    """Criterion 1: MCP write tool cannot bypass allow_order_submission kill-switch sentinel."""
    db_file = tmp_path / "mcp_write_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    settings = VolAgentSettings()
    # allow_order_submission is False by default
    assert settings.execution.allow_order_submission is False

    service = AlpacaMCPService(ledger=ledger, settings=settings)
    res = service.handle_tool_call(
        tool_name="alpaca_submit_multileg_order",
        arguments={"symbol": "NVDA", "quantity": 1, "limit_price": 4.50, "legs": []},
        decision_id="dec-write-01",
    )

    assert res["status"] == "REJECTED"

    # Audit recorded rejection
    audit_events = ledger.list_mcp_audit_events()
    assert len(audit_events) == 1
    assert audit_events[0]["result_status"] == "REJECTED"


def test_alpaca_mcp_routes_only_preapproved_canonical_plan(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "mcp_canonical.db")
    now = datetime.now(timezone.utc)
    expiry = date(2027, 9, 17)
    legs = [
        OptionLeg(contract_symbol="NVDA270917C00125000", option_type="call", strike=125.0,
                  expiration=expiry, side="buy", position_intent="buy_to_open", entry_price_assumption=5.0),
        OptionLeg(contract_symbol="NVDA270917P00125000", option_type="put", strike=125.0,
                  expiration=expiry, side="buy", position_intent="buy_to_open", entry_price_assumption=5.0),
    ]
    candidate = StrategyCandidate(
        strategy_id="strat-mcp-approved", decision=Decision.LONG_STRADDLE, legs=legs,
        quantity=1, entry_debit_credit=1000.0, max_loss=1000.0,
    )
    provenance = Provenance(
        source_name="Alpaca test quote", source_uri="mock://alpaca", retrieved_at=now,
        observed_at=now, content_hash="mcp-canonical", data_mode=DataMode.LIVE,
    )
    snapshots = {
        leg.contract_symbol: OptionContractSnapshot(
            symbol=leg.contract_symbol, underlying_symbol="NVDA", option_type=leg.option_type,
            strike=leg.strike, expiration=expiry, bid=4.95, ask=5.05,
            quote_time=now, provenance=provenance,
        ) for leg in legs
    }
    plan = build_order_plan(
        candidate, broker_target=BrokerTarget.ALPACA_PAPER, ledger=ledger,
        contract_snapshots=snapshots, decision_id="dec-mcp-approved", event_id="evt-mcp-approved",
    )
    decision_record = MagicMock()
    decision_record.decision_id = "dec-mcp-approved"
    decision_record.run_id = "run-mcp"
    decision_record.status = "APPROVED"
    decision_record.selected_action = Decision.LONG_STRADDLE.value
    decision_record.selected_strategy_id = candidate.strategy_id
    decision_record.quantity = 1
    decision_record.generated_at = now.isoformat()
    decision_record.artifact_hash = "hash-mcp"
    decision_record.snapshot = SimpleNamespace(symbol="NVDA")
    decision_record.model_dump.return_value = {
        "decision_id": "dec-mcp-approved", "status": "APPROVED", "symbol": "NVDA"
    }
    ledger.record_decision_record(decision_record)
    ledger.approve_order(plan.approval_token, actor="operator")
    receipt = ExecutionReceipt(
        receipt_id="receipt-mcp", client_order_id=plan.client_order_id,
        broker_order_id="paper-order-mcp", broker_target=BrokerTarget.ALPACA_PAPER,
        status=ExecutionStatus.ACCEPTED, submitted_at=now, fingerprint=plan.fingerprint,
    )
    service = AlpacaMCPService(
        ledger=ledger,
        settings=VolAgentSettings(alpaca_api_key="mock", alpaca_secret_key="mock"),
    )
    with patch.object(AlpacaPaperBroker, "submit_paper_order", return_value=receipt) as submit:
        result = service.handle_tool_call(
            "alpaca_submit_multileg_order",
            {"approval_token": plan.approval_token, "decision_id": "dec-mcp-approved"},
        )

    assert result["status"] == "SUCCESS"
    assert result["result"]["broker_order_id"] == "paper-order-mcp"
    submitted_plan = submit.call_args.args[0]
    assert submitted_plan.fingerprint == plan.fingerprint
    assert submitted_plan.decision_id == "dec-mcp-approved"


def test_cli_preflight_fails_closed_on_missing_credentials(tmp_path):
    """Criterion 2: CLI preflight returns HALTED when credentials or account snapshot are missing."""
    db_file = tmp_path / "preflight_noauth_test.db"
    receipt_file = tmp_path / "preflight_noauth_receipt.json"
    ledger = ExecutionLedger(db_path=db_file)

    settings = VolAgentSettings(alpaca_api_key="", alpaca_secret_key="")
    receipt = run_cli_preflight(
        settings=settings,
        ledger=ledger,
        output_path=receipt_file,
    )

    assert receipt["receipt_type"] == "caisheng.preflight.v1"
    assert receipt["overall_status"] == "HALTED"
    acct_chk = [c for c in receipt["checks"] if c["check"] == "account_accessibility"][0]
    assert acct_chk["status"] == "FAIL"
    assert receipt_file.exists()


def test_cli_preflight_passes_on_authenticated_paper_account(tmp_path):
    """Criterion 2: CLI preflight returns CLEAN when valid authenticated account snapshot exists."""
    db_file = tmp_path / "preflight_auth_test.db"
    receipt_file = tmp_path / "preflight_auth_receipt.json"
    ledger = ExecutionLedger(db_path=db_file)

    mock_adapter = MagicMock(spec=AlpacaPortfolioAdapter)
    mock_adapter.fetch_portfolio_snapshot.return_value = MagicMock(
        is_stale=False,
        account_id="ACC-PAPER-999",
        equity=100000.0,
        cash=50000.0,
        buying_power=200000.0,
        total_daily_pl=0.0,
        timestamp=datetime.now(timezone.utc),
    )

    settings = VolAgentSettings(alpaca_api_key="TEST_KEY", alpaca_secret_key="TEST_SEC", alpaca_paper_trade=True)
    receipt = run_cli_preflight(
        settings=settings,
        ledger=ledger,
        portfolio_adapter=mock_adapter,
        output_path=receipt_file,
    )

    assert receipt["receipt_type"] == "caisheng.preflight.v1"
    assert receipt["overall_status"] == "CLEAN"
    assert receipt["account"]["equity"] == 100000.0
    assert receipt["account"]["account_id"] == "ACC-PAPER-999"
    assert all(chk["status"] == "PASS" for chk in receipt["checks"])
    assert receipt_file.exists()


def test_cli_preflight_fails_closed_on_halt(tmp_path):
    """Criterion 2: CLI preflight trips HALTED status when system halt is active."""
    db_file = tmp_path / "preflight_halt_test.db"
    receipt_file = tmp_path / "preflight_halt_receipt.json"
    ledger = ExecutionLedger(db_path=db_file)

    # Trip persistent halt
    ledger.trip_system_halt(reason="Drawdown limit tripped")

    receipt = run_cli_preflight(
        ledger=ledger,
        output_path=receipt_file,
    )

    assert receipt["overall_status"] == "HALTED"
    halt_chk = [c for c in receipt["checks"] if c["check"] == "halt_state"][0]
    assert halt_chk["status"] == "FAIL"
    assert "Drawdown limit tripped" in halt_chk["details"]


def test_cli_reconciliation_generates_receipt(tmp_path):
    """Criterion 2: CLI reconciliation produces structured receipt and saves to disk."""
    db_file = tmp_path / "rec_test.db"
    receipt_file = tmp_path / "reconciliation_receipt.json"
    ledger = ExecutionLedger(db_path=db_file)

    receipt = run_cli_reconciliation(
        ledger=ledger,
        output_path=receipt_file,
    )

    assert receipt["receipt_type"] == "caisheng.daily_reconciliation.v1"
    assert "overall_status" in receipt
    assert receipt_file.exists()




def test_alpaca_mcp_transport_apps_expose_public_sdk_routes(tmp_path):
    """MCP transport apps expose working health and protocol routes."""
    from starlette.testclient import TestClient
    db_file = tmp_path / "mcp_sse_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    service = AlpacaMCPService(ledger=ledger)

    sse_app = service.create_sse_app()
    sse_client = TestClient(sse_app)
    response = sse_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["transport"] == "sse"
    assert {route.path for route in sse_app.routes} >= {"/sse", "/messages", "/healthz"}

    http_app = service.create_streamable_http_app()
    with TestClient(http_app) as http_client:
        response = http_client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["transport"] == "streamable-http"
        assert "/mcp" in {route.path for route in http_app.routes}

        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        initialized = http_client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "caisheng-test", "version": "1.0"},
                },
            },
        )
        assert initialized.status_code == 200
        assert initialized.headers.get("mcp-session-id")
        assert '"serverInfo"' in initialized.text

        headers["Mcp-Session-Id"] = initialized.headers["mcp-session-id"]
        notification = http_client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notification.status_code == 202
        tools = http_client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert tools.status_code == 200
        assert '"alpaca_get_option_chain"' in tools.text
