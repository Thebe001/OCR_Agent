"""Purchase invoice creation tool endpoint."""

import time

from fastapi import APIRouter

from app.models.errors import ErrorCode, MCPError
from app.models.schemas import CreatePurchaseInvoiceInput, build_success_response
from app.services.erpnext_client import ERPNextClient
from app.services.tenant_router import check_agent_entitlement, resolve_tenant

router = APIRouter(prefix="/tools", tags=["Invoice Tools"])
AGENT_ID = "invoice-ocr-agent"
TOOL_NAME = "create_purchase_invoice"
AMOUNT_TOLERANCE = 0.05


@router.post("/create_purchase_invoice")
async def create_purchase_invoice(input_data: CreatePurchaseInvoiceInput) -> dict:
    start = time.time()
    tenant = resolve_tenant(input_data.tenant_id)
    check_agent_entitlement(tenant, AGENT_ID)
    _validate_financial_data(input_data)

    client = ERPNextClient(tenant)
    await _check_duplicate_invoice(client, input_data)

    erpnext_data = _to_erpnext_purchase_invoice(input_data)
    result = await client.create_resource("Purchase Invoice", erpnext_data)
    created = result.get("data", {})
    invoice_id = created.get("name", "UNKNOWN")

    return build_success_response(
        TOOL_NAME,
        input_data.tenant_id,
        {
            "invoice_id": invoice_id,
            "status": "Draft",
            "supplier_name": input_data.supplier_name,
            "invoice_number": input_data.invoice_number,
            "invoice_date": input_data.invoice_date,
            "total_gross": input_data.total_gross,
            "currency": input_data.currency,
            "line_item_count": len(input_data.line_items),
            "message": "Draft purchase invoice created successfully. Please review and submit it in the Accounting module.",
        },
        int((time.time() - start) * 1000),
    )


def _validate_financial_data(input_data: CreatePurchaseInvoiceInput) -> None:
    if not input_data.confirmed:
        raise MCPError(
            ErrorCode.VALIDATION_ERROR,
            "Cannot create invoice: you must review and confirm the data first.",
            "confirmed must be true",
        )
    if input_data.vat_rate not in {0, 7, 19}:
        raise MCPError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid VAT rate. German VAT rates are 7% or 19%.",
        )
    if input_data.total_net < 0 or input_data.total_vat < 0 or input_data.total_gross < 0:
        raise MCPError(ErrorCode.VALIDATION_ERROR, "Invoice amounts cannot be negative.")

    expected_gross = round(input_data.total_net + input_data.total_vat, 2)
    if abs(expected_gross - round(input_data.total_gross, 2)) > AMOUNT_TOLERANCE:
        raise MCPError(
            ErrorCode.VALIDATION_ERROR,
            (
                f"The amounts don't add up: Net EUR {input_data.total_net:.2f} + "
                f"VAT EUR {input_data.total_vat:.2f} = EUR {expected_gross:.2f}, "
                f"but the invoice shows EUR {input_data.total_gross:.2f}."
            ),
        )

    for index, item in enumerate(input_data.line_items, start=1):
        if item.quantity <= 0:
            raise MCPError(ErrorCode.VALIDATION_ERROR, f"Line item {index} has an invalid quantity.")
        if item.unit_price < 0:
            raise MCPError(ErrorCode.VALIDATION_ERROR, f"Line item {index} has a negative price.")


def _to_erpnext_purchase_invoice(input_data: CreatePurchaseInvoiceInput) -> dict:
    items = []
    for item in input_data.line_items:
        row = {
            "item_name": item.description,
            "description": item.description,
            "qty": item.quantity,
            "rate": item.unit_price,
            "amount": item.total_price if item.total_price is not None else round(item.quantity * item.unit_price, 2),
        }
        if item.item_code:
            row["item_code"] = item.item_code
        items.append(row)

    data = {
        "doctype": "Purchase Invoice",
        "docstatus": 0,
        "supplier": input_data.supplier_name,
        "bill_no": input_data.invoice_number,
        "bill_date": input_data.invoice_date,
        "posting_date": input_data.invoice_date,
        "currency": input_data.currency,
        "items": items,
        "total": input_data.total_net,
        "grand_total": input_data.total_gross,
        "total_taxes_and_charges": input_data.total_vat,
    }
    if input_data.due_date:
        data["due_date"] = input_data.due_date
    return data


async def _check_duplicate_invoice(client: ERPNextClient, input_data: CreatePurchaseInvoiceInput) -> None:
    filters = [
        ["bill_no", "=", input_data.invoice_number],
        ["supplier", "=", input_data.supplier_name],
        ["bill_date", "=", input_data.invoice_date],
    ]
    try:
        rows = await client.list_resource(
            "Purchase Invoice",
            filters=filters,
            fields=["name", "bill_no", "supplier", "bill_date", "docstatus"],
            limit=1,
        )
    except MCPError as exc:
        if exc.code == ErrorCode.ERPNEXT_ERROR:
            # If duplicate check cannot be completed due to backend reachability,
            # continue with existing behavior.
            return
        raise

    if not rows:
        return

    existing = rows[0]
    raise MCPError(
        ErrorCode.VALIDATION_ERROR,
        "Possible duplicate invoice detected. A matching supplier/invoice number/date already exists.",
        f"existing_invoice={existing.get('name', 'UNKNOWN')}",
    )
