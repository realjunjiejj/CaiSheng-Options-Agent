"""Unit test for full interactive Streamlit UI rendering and lifecycle execution."""

from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_app_lifecycle_and_symbol_switching():
    """Verify Streamlit UI boots cleanly and handles symbol switching without unhandled exceptions."""
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run()
    assert len(at.exception) == 0

    # Test TSLA scenario switch
    for btn in at.button:
        if 'TSLA' in getattr(btn, 'label', ''):
            btn.click()
            at.run()
            break
    assert len(at.exception) == 0

    # Test AAPL scenario switch (rejection path)
    for btn in at.button:
        if 'AAPL' in getattr(btn, 'label', ''):
            btn.click()
            at.run()
            break
    assert len(at.exception) == 0
