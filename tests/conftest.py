"""Keep CLI decision records inside each test's temporary directory."""
import pytest


@pytest.fixture(autouse=True)
def isolated_decision_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_EFFORT_LEDGER", str(tmp_path / "decisions.sqlite3"))
