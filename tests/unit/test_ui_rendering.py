"""Unit test for full interactive Streamlit UI rendering and lifecycle execution."""

from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_app_lifecycle_and_symbol_switching():
    """Verify Streamlit UI boots cleanly and handles symbol switching without unhandled exceptions."""
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run()
    assert len(at.exception) == 0
    button_labels = {getattr(button, "label", "") for button in at.button}
    assert {
        "Start Autonomous Session",
        "Run Live Scan Now",
        "Stop New Entries",
        "Emergency Halt",
    }.issubset(button_labels)

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
    """Cloud Run judges see replay/evidence, never account or order controls."""
    monkeypatch.setenv("CAISHENG_PUBLIC_JUDGE_MODE", "true")
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run()

    assert len(at.exception) == 0
    assert list(at.radio[0].options) == ["01  Agent", "02  Evidence"]
    button_labels = {getattr(button, "label", "") for button in at.button}
    assert "Start Autonomous Session" not in button_labels
    assert "Submit Paper Order" not in button_labels
