"""Unit test for full interactive Streamlit UI rendering and lifecycle execution."""

from pathlib import Path
from streamlit.testing.v1 import AppTest

from volagent.config import load_config


def test_streamlit_app_lifecycle_and_symbol_switching():
    """Verify Streamlit UI boots cleanly and handles symbol switching without unhandled exceptions."""
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run()
    assert len(at.exception) == 0

    overview = " ".join(str(markdown.value) for markdown in at.markdown)
    assert "DECISION PATH" in overview

    at.radio[0].set_value("Operations")
    at.run()
    assert len(at.exception) == 0
    button_labels = {getattr(button, "label", "") for button in at.button}
    assert {
        "Start Autonomous Session",
        "Run Live Scan Now",
        "Stop New Entries",
        "Emergency Halt",
    }.issubset(button_labels)

    at.radio[0].set_value("Agent")
    at.run()
    assert len(at.exception) == 0

    # Test TSLA scenario switch
    for btn in at.button:
        if "TSLA" in getattr(btn, "label", ""):
            btn.click()
            at.run()
            break
    assert len(at.exception) == 0

    # Test AAPL scenario switch (rejection path)
    for btn in at.button:
        if "AAPL" in getattr(btn, "label", ""):
            btn.click()
            at.run()
            break
    assert len(at.exception) == 0


def test_public_judge_mode_is_credential_free_and_read_only(monkeypatch):
    """Cloud Run judges see concise replay/evidence, never account or order controls."""
    monkeypatch.setenv("CAISHENG_PUBLIC_JUDGE_MODE", "true")
    original_replay_scenario = load_config().volagent_replay_scenario_id
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run()

    assert len(at.exception) == 0
    assert list(at.radio[0].options) == ["01  Overview", "02  Agent", "03  Results"]
    button_labels = {getattr(button, "label", "") for button in at.button}
    assert "Start Autonomous Session" not in button_labels
    assert "Submit Paper Order" not in button_labels
    assert "Approve Plan Token" not in button_labels
    assert "Execute in Local Simulator" not in button_labels
    rendered = " ".join(str(markdown.value) for markdown in at.markdown)
    assert "DECISION PATH" in rendered
    assert "Trading API" in rendered
    assert "FastMCP" in rendered

    at.radio[0].set_value("Agent")
    at.run()
    button_labels = {getattr(button, "label", "") for button in at.button}
    assert {
        "NVDA · Long volatility",
        "TSLA · Short volatility",
        "AAPL · Abstain",
    }.issubset(button_labels)

    rendered = " ".join(str(markdown.value) for markdown in at.markdown)
    assert "ALPACA · OPTIONS ALPHA" in rendered
    assert "ALPACA API · MCP · CLI" in rendered
    assert "CONTROLLED REPLAY" in rendered
    assert "SHORT VOL ADVOCATE" in rendered
    assert "MODEL-RISK CRITIC" in rendered
    assert "TRACK 02" not in rendered
    assert "PUBLIC JUDGE DEMO" not in rendered
    assert "PAPER ARMED" not in rendered
    assert "FAST-MCP V2 LIVE" not in rendered

    next(button for button in at.button if button.label == "TSLA · Short volatility").click()
    at.run()
    assert len(at.exception) == 0
    rendered = " ".join(str(markdown.value) for markdown in at.markdown)
    assert "SCENARIO-TSLA-2024Q3-AMC" in rendered
    assert "short iron butterfly" in rendered

    next(button for button in at.button if button.label == "AAPL · Abstain").click()
    at.run()
    assert len(at.exception) == 0
    rendered = " ".join(str(markdown.value) for markdown in at.markdown)
    assert "SCENARIO-AAPL-2024Q4-STALE" in rendered
    assert "no trade" in rendered
    assert load_config().volagent_replay_scenario_id == original_replay_scenario
