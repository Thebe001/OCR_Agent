"""MCP tool implementation: get_pos_transactions."""

from __future__ import annotations

from src.services.mock_data.mock_data_loader import get_data_source, load_pos_invoices


def execute(date: str, pos_profile: str | None = None) -> dict:
    """Retrieve POS invoices for a date/profile and compute summary metrics."""
    invoices = load_pos_invoices(date=date, pos_profile=pos_profile)
    total_sales = round(sum(float(inv.get("total", 0.0)) for inv in invoices), 2)

    cashier_breakdown: dict[str, float] = {}
    for inv in invoices:
        cashier = str(inv.get("cashier", "Unknown"))
        cashier_breakdown[cashier] = cashier_breakdown.get(cashier, 0.0) + float(inv.get("total", 0.0))

    return {
        "date": date,
        "data_source": get_data_source(),
        "pos_profile": pos_profile or "All",
        "transaction_count": len(invoices),
        "total_sales": total_sales,
        "cashier_breakdown": {key: round(value, 2) for key, value in cashier_breakdown.items()},
        "invoices": invoices,
    }
