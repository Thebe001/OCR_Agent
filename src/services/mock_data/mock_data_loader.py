"""Mock data loader for Daily Close Agent.

Swap point: replace these functions with ERPNext REST calls when production
connectivity is available. All business logic stays unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DATA_DIR = Path(__file__).parent


def _read_json(file_name: str) -> Any:
    with (DATA_DIR / file_name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_data_source() -> str:
    """Return configured data source: mock or erpnext."""
    source = os.getenv("DAILY_CLOSE_DATA_SOURCE", "mock").strip().lower()
    return source if source in {"mock", "erpnext"} else "mock"


def _erp_credentials() -> tuple[str, str, str]:
    base_url = os.getenv("DAILY_CLOSE_ERPNEXT_BASE_URL", os.getenv("ERPNEXT_BASE_URL", "")).strip().rstrip("/")
    api_key = os.getenv("DAILY_CLOSE_ERPNEXT_API_KEY", os.getenv("ERPNEXT_API_KEY", "")).strip()
    api_secret = os.getenv("DAILY_CLOSE_ERPNEXT_API_SECRET", os.getenv("ERPNEXT_API_SECRET", "")).strip()
    if not base_url or not api_key or not api_secret:
        raise RuntimeError(
            "Daily Close real-data mode requires DAILY_CLOSE_ERPNEXT_BASE_URL, "
            "DAILY_CLOSE_ERPNEXT_API_KEY, and DAILY_CLOSE_ERPNEXT_API_SECRET."
        )
    return base_url, api_key, api_secret


def _erp_request(path: str, params: dict[str, Any] | None = None) -> dict:
    base_url, api_key, api_secret = _erp_credentials()
    headers = {"Authorization": f"token {api_key}:{api_secret}", "Accept": "application/json"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{base_url}{path}", params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def _load_pos_invoices_mock(date: str, pos_profile: str | None = None) -> list[dict]:
    invoices = _read_json("pos_invoices.json")
    filtered = [inv for inv in invoices if inv.get("posting_date") == date]
    if pos_profile:
        filtered = [inv for inv in filtered if inv.get("pos_profile") == pos_profile]
    return filtered


def _load_pos_invoices_erpnext(date: str, pos_profile: str | None = None) -> list[dict]:
    filters = [["posting_date", "=", date]]
    if pos_profile:
        filters.append(["pos_profile", "=", pos_profile])

    fields = [
        "name",
        "posting_date",
        "posting_time",
        "customer",
        "owner",
        "pos_profile",
        "grand_total",
        "paid_amount",
        "status",
    ]
    params = {
        "filters": json.dumps(filters),
        "fields": json.dumps(fields),
        "limit_page_length": 1000,
    }
    rows = _erp_request("/api/resource/POS Invoice", params=params).get("data", [])

    normalized: list[dict] = []
    for row in rows:
        name = str(row.get("name", ""))
        detail = _erp_request(f"/api/resource/POS Invoice/{name}").get("data", {})

        items = []
        for item in detail.get("items", []):
            qty = float(item.get("qty") or 0.0)
            rate = float(item.get("rate") or 0.0)
            amount = float(item.get("amount") or round(qty * rate, 2))
            items.append(
                {
                    "item_code": item.get("item_code") or item.get("item_name") or "UNKNOWN",
                    "item_name": item.get("item_name") or item.get("item_code") or "Unknown Item",
                    "qty": qty,
                    "rate": rate,
                    "amount": amount,
                }
            )

        payments = []
        for p in detail.get("payments", []):
            payments.append(
                {
                    "mode_of_payment": p.get("mode_of_payment") or "Unknown",
                    "amount": float(p.get("amount") or p.get("base_amount") or 0.0),
                }
            )

        if not payments and float(row.get("paid_amount") or 0.0) != 0.0:
            payments = [{"mode_of_payment": "Unknown", "amount": float(row.get("paid_amount") or 0.0)}]

        normalized.append(
            {
                "invoice_id": name,
                "posting_date": detail.get("posting_date") or row.get("posting_date") or date,
                "posting_time": detail.get("posting_time") or row.get("posting_time") or "00:00:00",
                "customer": detail.get("customer") or row.get("customer") or "Walk-in Customer",
                "cashier": detail.get("owner") or row.get("owner") or "Unknown",
                "pos_profile": detail.get("pos_profile") or row.get("pos_profile") or (pos_profile or "Unknown POS"),
                "items": items,
                "total": float(detail.get("grand_total") or detail.get("total") or row.get("grand_total") or 0.0),
                "payments": payments,
                "status": detail.get("status") or row.get("status") or "Unknown",
            }
        )
    return normalized


def _load_payment_summary_mock(date: str) -> dict:
    payload = _read_json("pos_payments.json")
    if payload.get("date") != date:
        return {**payload, "payment_summary": []}
    return payload


def _load_payment_summary_erpnext(date: str) -> dict:
    invoices = _load_pos_invoices_erpnext(date=date, pos_profile=None)
    mode_totals: dict[str, float] = {}
    for inv in invoices:
        for payment in inv.get("payments", []):
            mode = str(payment.get("mode_of_payment", "Unknown"))
            mode_totals[mode] = mode_totals.get(mode, 0.0) + float(payment.get("amount", 0.0))

    opening_balance = float(os.getenv("DAILY_CLOSE_OPENING_BALANCE", "0") or 0.0)
    cash_collected = mode_totals.get("Cash", 0.0)

    actual_cash_env = os.getenv("DAILY_CLOSE_ACTUAL_CASH_COUNTED")
    if actual_cash_env is None or not actual_cash_env.strip():
        actual_cash = opening_balance + cash_collected
    else:
        actual_cash = float(actual_cash_env)

    return {
        "date": date,
        "pos_profile": os.getenv("DAILY_CLOSE_POS_PROFILE", "All"),
        "expected_cash_in_drawer": round(opening_balance + cash_collected, 2),
        "actual_cash_counted": round(actual_cash, 2),
        "payment_summary": [
            {"mode_of_payment": mode, "total_collected": round(total, 2)}
            for mode, total in sorted(mode_totals.items())
        ],
        "opening_balance": round(opening_balance, 2),
        "source_note": "Generated from POS invoices. For exact drawer count, set DAILY_CLOSE_ACTUAL_CASH_COUNTED.",
    }


def _load_stock_levels_mock() -> list[dict]:
    return _read_json("stock_levels.json")


def _load_stock_levels_erpnext() -> list[dict]:
    fields = ["item_code", "warehouse", "actual_qty", "reserved_qty"]
    rows = _erp_request(
        "/api/resource/Bin",
        params={"fields": json.dumps(fields), "limit_page_length": 5000},
    ).get("data", [])

    return [
        {
            "item_code": row.get("item_code") or "UNKNOWN",
            "item_name": row.get("item_code") or "Unknown Item",
            "warehouse": row.get("warehouse") or "Unknown Warehouse",
            "actual_qty": float(row.get("actual_qty") or 0.0),
            "reserved_qty": float(row.get("reserved_qty") or 0.0),
        }
        for row in rows
    ]


def load_pos_invoices(date: str, pos_profile: str | None = None) -> list[dict]:
    """Load POS invoices for a date, optionally filtered by POS profile."""
    if get_data_source() == "erpnext":
        return _load_pos_invoices_erpnext(date=date, pos_profile=pos_profile)
    return _load_pos_invoices_mock(date=date, pos_profile=pos_profile)


def load_payment_summary(date: str) -> dict:
    """Load payment summary for a date from mock source."""
    if get_data_source() == "erpnext":
        return _load_payment_summary_erpnext(date=date)
    return _load_payment_summary_mock(date=date)


def load_stock_levels() -> list[dict]:
    """Load current stock levels from mock source."""
    if get_data_source() == "erpnext":
        return _load_stock_levels_erpnext()
    return _load_stock_levels_mock()
