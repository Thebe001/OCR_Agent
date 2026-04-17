"""MCP tool implementation: detect_anomalies."""

from __future__ import annotations

from src.anomaly_engine.detector import generate_summary, run_all_checks
from src.services.mock_data.mock_data_loader import (
    get_data_source,
    load_payment_summary,
    load_pos_invoices,
    load_stock_levels,
)


def execute(date: str) -> dict:
    """Run anomaly engine for the selected day and return details + summary."""
    invoices = load_pos_invoices(date=date)
    payment_data = load_payment_summary(date=date)
    stock_levels = load_stock_levels()

    anomalies = run_all_checks(
        invoices=invoices,
        stock_levels=stock_levels,
        payment_data=payment_data,
    )
    summary = generate_summary(anomalies)

    return {
        "date": date,
        "data_source": get_data_source(),
        "summary": summary,
        "anomalies": anomalies,
    }
