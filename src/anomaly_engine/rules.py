"""Daily close anomaly rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    CASH_MISMATCH = "CASH_MISMATCH"
    NEGATIVE_STOCK = "NEGATIVE_STOCK"
    MISSING_INVOICE = "MISSING_INVOICE"
    NEGATIVE_TRANSACTION = "NEGATIVE_TRANSACTION"
    DRAWER_DISCREPANCY = "DRAWER_DISCREPANCY"


@dataclass
class Anomaly:
    anomaly_type: str
    severity: str
    explanation: str
    source_invoice: str | None = None
    source_item: str | None = None
    expected_value: float | None = None
    actual_value: float | None = None

    def to_dict(self) -> dict:
        payload = {k: v for k, v in asdict(self).items() if v is not None}
        payload["anomaly_type"] = str(payload["anomaly_type"])
        payload["severity"] = str(payload["severity"])
        return payload


def check_cash_mismatch(invoices: list[dict]) -> list[Anomaly]:
    """Detect mismatches between invoice total and payment total."""
    anomalies: list[Anomaly] = []
    for inv in invoices:
        invoice_total = float(inv.get("total", 0.0))
        payment_total = float(sum(float(p.get("amount", 0.0)) for p in inv.get("payments", [])))
        if abs(payment_total - invoice_total) > 0.01:
            diff = payment_total - invoice_total
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.CASH_MISMATCH.value,
                    severity=(Severity.HIGH.value if abs(diff) > 5 else Severity.MEDIUM.value),
                    explanation=(
                        f"Invoice {inv.get('invoice_id')}: payment total ({payment_total:.2f} EUR) "
                        f"does not match invoice total ({invoice_total:.2f} EUR). "
                        f"Difference: {diff:+.2f} EUR"
                    ),
                    source_invoice=inv.get("invoice_id"),
                    expected_value=invoice_total,
                    actual_value=payment_total,
                )
            )
    return anomalies


def check_negative_stock(stock_levels: list[dict]) -> list[Anomaly]:
    """Detect items with negative stock quantity."""
    anomalies: list[Anomaly] = []
    for item in stock_levels:
        actual_qty = float(item.get("actual_qty", 0.0))
        if actual_qty < 0:
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.NEGATIVE_STOCK.value,
                    severity=Severity.CRITICAL.value,
                    explanation=(
                        f"Item '{item.get('item_name')}' ({item.get('item_code')}) has negative stock: "
                        f"{actual_qty:g} in warehouse '{item.get('warehouse')}'."
                    ),
                    source_item=item.get("item_code"),
                    expected_value=0.0,
                    actual_value=actual_qty,
                )
            )
    return anomalies


def check_missing_invoices(invoices: list[dict]) -> list[Anomaly]:
    """Detect gaps in sequential invoice numbering."""
    anomalies: list[Anomaly] = []
    if not invoices:
        return anomalies

    try:
        number_pairs: list[tuple[int, str]] = []
        for inv in invoices:
            inv_id = str(inv.get("invoice_id", ""))
            number_pairs.append((int(inv_id.split("-")[-1]), inv_id))
        number_pairs.sort()

        prefix = "-".join(number_pairs[0][1].split("-")[:-1])
        for i in range(len(number_pairs) - 1):
            curr_num = number_pairs[i][0]
            next_num = number_pairs[i + 1][0]
            if next_num - curr_num > 1:
                for missing in range(curr_num + 1, next_num):
                    missing_id = f"{prefix}-{missing:03d}"
                    anomalies.append(
                        Anomaly(
                            anomaly_type=AnomalyType.MISSING_INVOICE.value,
                            severity=Severity.HIGH.value,
                            explanation=(
                                f"Invoice '{missing_id}' is missing from sequence between "
                                f"{number_pairs[i][1]} and {number_pairs[i + 1][1]}."
                            ),
                            source_invoice=missing_id,
                        )
                    )
    except (ValueError, IndexError):
        return anomalies

    return anomalies


def check_negative_transactions(invoices: list[dict]) -> list[Anomaly]:
    """Detect suspicious negative-total POS invoices."""
    anomalies: list[Anomaly] = []
    for inv in invoices:
        total = float(inv.get("total", 0.0))
        if total < 0:
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.NEGATIVE_TRANSACTION.value,
                    severity=Severity.HIGH.value,
                    explanation=(
                        f"Invoice {inv.get('invoice_id')} has negative total {total:.2f} EUR. "
                        f"Cashier: {inv.get('cashier')}."
                    ),
                    source_invoice=inv.get("invoice_id"),
                    expected_value=0.0,
                    actual_value=total,
                )
            )
    return anomalies


def check_drawer_discrepancy(payment_data: dict) -> list[Anomaly]:
    """Detect mismatch between expected and physically counted cash drawer."""
    anomalies: list[Anomaly] = []
    cash_collected = 0.0
    for entry in payment_data.get("payment_summary", []):
        if entry.get("mode_of_payment") == "Cash":
            cash_collected = float(entry.get("total_collected", 0.0))

    opening_balance = float(payment_data.get("opening_balance", 0.0))
    expected_drawer = opening_balance + cash_collected
    actual_drawer = float(payment_data.get("actual_cash_counted", 0.0))

    if abs(expected_drawer - actual_drawer) > 0.01:
        diff = actual_drawer - expected_drawer
        anomalies.append(
            Anomaly(
                anomaly_type=AnomalyType.DRAWER_DISCREPANCY.value,
                severity=(Severity.CRITICAL.value if abs(diff) > 10 else Severity.HIGH.value),
                explanation=(
                    f"Cash drawer discrepancy. Expected {expected_drawer:.2f} EUR, "
                    f"actual {actual_drawer:.2f} EUR, difference {diff:+.2f} EUR."
                ),
                expected_value=expected_drawer,
                actual_value=actual_drawer,
            )
        )

    return anomalies
