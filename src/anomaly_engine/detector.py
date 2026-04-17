"""Anomaly detector orchestrating all rule checks."""

from __future__ import annotations

from src.anomaly_engine.rules import (
    Anomaly,
    check_cash_mismatch,
    check_drawer_discrepancy,
    check_missing_invoices,
    check_negative_stock,
    check_negative_transactions,
)


def run_all_checks(invoices: list[dict], stock_levels: list[dict], payment_data: dict) -> list[dict]:
    """Run all anomaly checks and return sorted anomaly dictionaries."""
    collected: list[Anomaly] = []
    collected.extend(check_cash_mismatch(invoices))
    collected.extend(check_negative_stock(stock_levels))
    collected.extend(check_missing_invoices(invoices))
    collected.extend(check_negative_transactions(invoices))
    collected.extend(check_drawer_discrepancy(payment_data))

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    collected.sort(key=lambda a: order.get(a.severity, 99))
    return [item.to_dict() for item in collected]


def generate_summary(anomalies: list[dict]) -> dict:
    """Build aggregate summary for detected anomalies."""
    total = len(anomalies)
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for anomaly in anomalies:
        severity = anomaly.get("severity", "unknown")
        anomaly_type = anomaly.get("anomaly_type", "UNKNOWN")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1

    return {
        "total_anomalies": total,
        "by_severity": by_severity,
        "by_type": by_type,
        "safe_to_close": total == 0,
        "recommendation": (
            "All checks passed. Safe to close POS session."
            if total == 0
            else f"Found {total} anomaly(s). Review required before closing session."
        ),
    }
