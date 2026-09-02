"""Pytest fixtures and configuration ensuring complete environment and ledger isolation."""

import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_test_ledger(tmp_path_factory, monkeypatch):
    """Automatically isolate ExecutionLedger DB path and runtime lock for every test run."""
    test_db_dir = tmp_path_factory.mktemp("ledger_db")
    test_db_file = test_db_dir / "isolated_test_ledger.db"
    test_lock_file = test_db_dir / "caisheng_runtime.lock"
    monkeypatch.setenv("VOLAGENT_LEDGER_DB_PATH", str(test_db_file))
    monkeypatch.setenv("VOLAGENT_RUNTIME_LOCK_PATH", str(test_lock_file))
    yield test_db_file

