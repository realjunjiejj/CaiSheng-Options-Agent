"""Acceptance tests for the Alpaca multi-agent architecture evidence contract."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from volagent.config import load_config
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter
from volagent.domain.state import EventMagnitudeAssessment, VolatilityThesis
from volagent.graph.builder import VolAgentWorkflow
from volagent.ui.integration_status import judge_workspaces


class _StructuredResponder:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, _messages):
        if self.schema is EventMagnitudeAssessment:
            return EventMagnitudeAssessment(
                event_novelty_score=0.6,
                guidance_uncertainty_score=0.7,
                analyst_dispersion_score=0.5,
                magnitude_pressure_score=0.62,
                confidence=0.8,
                supporting_evidence_ids=[],
                summary="Grounded structured assessment.",
            )
        side = "long_vol" if "Long" in _messages[0]["content"] else "short_vol"
        return VolatilityThesis(
            side=side,
            thesis=f"Structured {side} thesis.",
            numeric_argument="Evidence-bound volatility comparison.",
            supporting_evidence_ids=[],
            invalidation_conditions=["The volatility edge disappears."],
            confidence=0.7,
        )


class _SuccessfulLLM:
    model_name = "judge-test-model"

    def with_structured_output(self, schema):
        return _StructuredResponder(schema)


class _FailingResponder:
    def invoke(self, _messages):
        raise TimeoutError("simulated provider timeout")


class _FailingLLM:
    model_name = "judge-test-model"

    def with_structured_output(self, _schema):
        return _FailingResponder()


def _workflow(llm_client=None):
    config = load_config()
    config.volagent_replay_scenario_id = "SCENARIO-NVDA-2024Q2-AMC"
    return VolAgentWorkflow(config=config, llm_client=llm_client)


def test_decision_proves_deterministic_agent_runtime_and_replay_feeds():
    result = _workflow().run({"symbol": "NVDA"})

    runtime = result["decision_record"].agent_runtime
    snapshot = result["decision_record"].snapshot

    assert runtime.mode == "deterministic"
    assert runtime.llm_requested is False
    assert runtime.model_identifier is None
    assert {component.name for component in runtime.components} >= {
        "event_magnitude",
        "long_vol_advocate",
        "short_vol_advocate",
        "model_risk_critic",
    }
    assert snapshot.stock_feed == "replay_synthetic"
    assert snapshot.options_feed == "replay_synthetic"
    assert snapshot.options_feed_is_indicative is False


def test_decision_proves_successful_llm_participation_without_giving_it_authority():
    result = _workflow(llm_client=_SuccessfulLLM()).run({"symbol": "NVDA"})

    runtime = result["decision_record"].agent_runtime

    assert runtime.mode == "llm_assisted"
    assert runtime.llm_requested is True
    assert runtime.model_identifier == "judge-test-model"
    assert runtime.fallback_nodes == []
    assert set(runtime.llm_nodes_succeeded) == {
        "event_magnitude",
        "long_vol_advocate",
        "short_vol_advocate",
    }
    assert "pricing" in runtime.deterministic_authority
    assert "execution" in runtime.deterministic_authority


def test_decision_labels_llm_failure_and_deterministic_fallback():
    result = _workflow(llm_client=_FailingLLM()).run({"symbol": "NVDA"})

    runtime = result["decision_record"].agent_runtime

    assert runtime.mode == "deterministic_fallback"
    assert runtime.llm_requested is True
    assert set(runtime.fallback_nodes) == {
        "event_magnitude",
        "long_vol_advocate",
        "short_vol_advocate",
    }
    assert all(
        component.error_type == "TimeoutError"
        for component in runtime.components
        if component.name in runtime.fallback_nodes
    )


def test_competition_config_explicitly_selects_conservative_alpaca_feeds():
    settings = load_config("config/competition.yaml")

    assert settings.market_data.stock_feed == "iex"
    assert settings.market_data.options_feed == "indicative"


def test_public_judge_app_exposes_only_credential_free_workspaces():
    assert judge_workspaces(public_read_only=True) == ("Agent", "Evidence")
    assert judge_workspaces(public_read_only=False) == (
        "Command",
        "Agent",
        "Paper Trade",
        "Evidence",
    )


def test_live_option_chain_requests_and_persists_the_declared_feed(monkeypatch):
    symbol = "SPY260918C00650000"
    captured = {}

    monkeypatch.setattr(
        "alpaca.trading.client.TradingClient.get_option_contracts",
        lambda _client, _request: SimpleNamespace(option_contracts=[SimpleNamespace(
            symbol=symbol,
            tradable=True,
            underlying_symbol="SPY",
            open_interest="1000",
        )]),
    )

    def fake_chain(_client, request):
        captured["feed"] = request.feed.value
        return {
            symbol: SimpleNamespace(
                latest_quote=SimpleNamespace(
                    bid_price=5.0,
                    ask_price=5.1,
                    timestamp=datetime.now(timezone.utc),
                ),
                implied_volatility=0.22,
                greeks=SimpleNamespace(
                    delta=0.5,
                    gamma=0.01,
                    theta=-0.1,
                    vega=0.2,
                ),
            )
        }

    monkeypatch.setattr(
        "alpaca.data.historical.OptionHistoricalDataClient.get_option_chain",
        fake_chain,
    )
    monkeypatch.setattr(
        AlpacaLiveMarketAdapter,
        "_option_volumes",
        lambda _self, _client, _symbols: {symbol: 500},
    )

    adapter = AlpacaLiveMarketAdapter(
        "paper-key",
        "paper-secret",
        stock_feed="iex",
        options_feed="indicative",
    )
    chain = adapter.get_option_chain(
        "SPY",
        earliest_expiration=date(2026, 9, 18),
        latest_expiration=date(2026, 9, 18),
        spot_price=650.0,
    )

    assert captured["feed"] == "indicative"
    assert len(chain) == 1
    assert chain[0].data_feed == "indicative"
