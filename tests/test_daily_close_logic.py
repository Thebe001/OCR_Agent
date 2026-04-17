import re

from src.tools.daily_close.close_pos_session import execute as close_pos_session_execute
from src.tools.daily_close.detect_anomalies import execute as detect_anomalies_execute
from src.tools.daily_close.get_pos_transactions import execute as get_pos_transactions_execute
from src.tools.daily_close.validate_pos_totals import execute as validate_pos_totals_execute


def test_get_pos_transactions_summary_uses_mock_dataset(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")

    result = get_pos_transactions_execute(date="2025-04-17")

    assert result["data_source"] == "mock"
    assert result["transaction_count"] == 5
    assert result["total_sales"] == 103.0
    assert result["cashier_breakdown"] == {
        "Marie Dupont": 73.0,
        "Pierre Bernard": 30.0,
    }


def test_validate_pos_totals_detects_mismatch(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")

    result = validate_pos_totals_execute(date="2025-04-17")

    assert result["data_source"] == "mock"
    assert result["invoice_total"] == 103.0
    assert result["payment_total"] == 104.0
    assert result["difference"] == 1.0
    assert result["is_valid"] is False
    assert "Discrepancy detected" in result["validation_message"]


def test_detect_anomalies_returns_expected_summary(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")

    result = detect_anomalies_execute(date="2025-04-17")

    assert result["data_source"] == "mock"
    summary = result["summary"]
    assert summary["total_anomalies"] == 4
    assert summary["safe_to_close"] is False
    assert summary["by_severity"] == {
        "critical": 1,
        "high": 2,
        "medium": 1,
    }
    assert summary["by_type"] == {
        "NEGATIVE_STOCK": 1,
        "NEGATIVE_TRANSACTION": 1,
        "DRAWER_DISCREPANCY": 1,
        "CASH_MISMATCH": 1,
    }


def test_close_pos_session_blocked_without_force_close(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")

    result = close_pos_session_execute(date="2025-04-17", force_close=False)

    assert result["status"] == "BLOCKED"
    assert result["data_source"] == "mock"
    assert "Cannot close session" in result["reason"]
    assert result["anomaly_summary"]["total_anomalies"] == 4


def test_close_pos_session_force_close_when_anomalies_exist(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")

    result = close_pos_session_execute(date="2025-04-17", force_close=True)

    assert result["status"] == "FORCE_CLOSED"
    assert result["data_source"] == "mock"
    assert result["anomalies_overridden"] == 4
    assert re.match(r"^POS-CLO-20250417-001$", result["closing_entry_id"])


def test_close_pos_session_closed_when_no_anomalies(monkeypatch):
    monkeypatch.setenv("DAILY_CLOSE_DATA_SOURCE", "mock")
    monkeypatch.setattr("src.tools.daily_close.close_pos_session.run_all_checks", lambda **_: [])

    result = close_pos_session_execute(date="2025-04-17", force_close=False)

    assert result["status"] == "CLOSED"
    assert result["data_source"] == "mock"
    assert result["anomalies_overridden"] == 0
    assert result["message"].startswith("POS session closed successfully")
