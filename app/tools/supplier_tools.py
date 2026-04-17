"""Supplier validation tool endpoint."""

import time

from fastapi import APIRouter

from app.models.errors import ErrorCode, MCPError
from app.models.schemas import ValidateSupplierInput, build_success_response
from app.services.erpnext_client import ERPNextClient
from app.services.tenant_router import check_agent_entitlement, resolve_tenant

router = APIRouter(prefix="/tools", tags=["Supplier Tools"])
AGENT_ID = "invoice-ocr-agent"
TOOL_NAME = "validate_supplier"


@router.post("/validate_supplier")
async def validate_supplier(input_data: ValidateSupplierInput) -> dict:
    start = time.time()
    tenant = resolve_tenant(input_data.tenant_id)
    check_agent_entitlement(tenant, AGENT_ID)

    supplier_name = input_data.supplier_name.strip()
    if not supplier_name:
        raise MCPError(ErrorCode.VALIDATION_ERROR, "Supplier name is required.")

    client = ERPNextClient(tenant)
    try:
        result = await client.get_resource("Supplier", supplier_name)
        supplier = result.get("data", {})
        data = {
            "found": True,
            "supplier_id": supplier.get("name", supplier_name),
            "supplier_name": supplier.get("supplier_name", supplier_name),
            "supplier_group": supplier.get("supplier_group", ""),
            "address": supplier.get("supplier_primary_address", ""),
            "tax_id": supplier.get("tax_id", ""),
            "default_currency": supplier.get("default_currency", "EUR"),
            "status": "Active" if supplier.get("disabled", 0) == 0 else "Inactive",
        }
    except MCPError as exc:
        if exc.code != ErrorCode.NOT_FOUND:
            raise
        suggestions = await _supplier_suggestions(client, supplier_name)
        data = {
            "found": False,
            "searched_name": supplier_name,
            "suggestions": suggestions,
        }

    return build_success_response(
        TOOL_NAME,
        input_data.tenant_id,
        data,
        int((time.time() - start) * 1000),
    )


async def _supplier_suggestions(client: ERPNextClient, supplier_name: str) -> list[dict]:
    try:
        rows = await client.list_resource(
            "Supplier",
            filters=[["supplier_name", "like", f"%{supplier_name[:10]}%"]],
            fields=["name", "supplier_name"],
            limit=3,
        )
    except Exception:
        return []
    return [
        {
            "supplier_name": row.get("supplier_name", row.get("name", "")),
            "similarity_score": 0.75,
        }
        for row in rows
    ]
