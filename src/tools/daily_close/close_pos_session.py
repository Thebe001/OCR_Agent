"""MCP tool implementation: close_pos_session."""

from __future__ import annotations

from datetime import datetime

from src.anomaly_engine.detector import generate_summary, run_all_checks
from src.services.mock_data.mock_data_loader import (
    get_data_source,
    load_payment_summary,
    load_pos_invoices,
    load_stock_levels,
)


def execute(date: str, force_close: bool = False) -> dict:
    """Attempt session closing; block on anomalies unless force_close is true."""
    invoices = load_pos_invoices(date=date)
    payment_data = load_payment_summary(date=date)
    stock_levels = load_stock_levels()

    anomalies = run_all_checks(
        invoices=invoices,
        stock_levels=stock_levels,
        payment_data=payment_data,
    )
    summary = generate_summary(anomalies)

    if anomalies and not force_close:
        return {
            "status": "BLOCKED",
            "data_source": get_data_source(),
            "reason": f"Cannot close session: {summary['total_anomalies']} anomaly(s) detected.",
            "anomaly_summary": summary,
            "hint": "Run detect_anomalies, review issues, and retry with force_close=true if needed.",
        }

    closing_entry_id = f"POS-CLO-{date.replace('-', '')}-001"
    total_sales = round(sum(float(inv.get("total", 0.0)) for inv in invoices), 2)

    return {
        "status": "FORCE_CLOSED" if anomalies else "CLOSED",
        "data_source": get_data_source(),
        "closing_entry_id": closing_entry_id,
        "date": date,
        "pos_profile": "Floravi Shop 1",
        "transaction_count": len(invoices),
        "total_sales": total_sales,
        "closed_at": datetime.now().isoformat(),
        "closed_by": "Daily Close Agent (V1 Mock)",
        "anomalies_overridden": len(anomalies) if force_close else 0,
        "message": (
            f"POS session closed successfully. Entry: {closing_entry_id}"
            if not anomalies
            else f"POS session force-closed with {len(anomalies)} anomaly(s) overridden."
        ),
    }
