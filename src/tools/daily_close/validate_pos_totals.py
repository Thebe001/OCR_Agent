"""MCP tool implementation: validate_pos_totals."""

from __future__ import annotations

from src.services.mock_data.mock_data_loader import get_data_source, load_payment_summary, load_pos_invoices


def execute(date: str) -> dict:
    """Validate invoice totals against payment summary totals for a given day."""
    invoices = load_pos_invoices(date=date)
    payment_data = load_payment_summary(date=date)

    invoice_total = sum(float(inv.get("total", 0.0)) for inv in invoices)
    payment_total = sum(float(p.get("total_collected", 0.0)) for p in payment_data.get("payment_summary", []))

    invoice_mode_breakdown: dict[str, float] = {}
    for inv in invoices:
        for p in inv.get("payments", []):
            mode = str(p.get("mode_of_payment", "Unknown"))
            invoice_mode_breakdown[mode] = invoice_mode_breakdown.get(mode, 0.0) + float(p.get("amount", 0.0))

    diff = round(payment_total - invoice_total, 2)
    is_valid = abs(diff) < 0.01

    return {
        "date": date,
        "data_source": get_data_source(),
        "invoice_total": round(invoice_total, 2),
        "payment_total": round(payment_total, 2),
        "difference": diff,
        "is_valid": is_valid,
        "mode_breakdown_from_invoices": {k: round(v, 2) for k, v in invoice_mode_breakdown.items()},
        "mode_breakdown_from_payments": {
            str(p.get("mode_of_payment", "Unknown")): float(p.get("total_collected", 0.0))
            for p in payment_data.get("payment_summary", [])
        },
        "validation_message": (
            "Totals match. Validation passed."
            if is_valid
            else f"Discrepancy detected: {diff:+.2f} EUR"
        ),
    }
