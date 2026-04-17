"""Item validation tool endpoint."""

import time

from fastapi import APIRouter

from app.models.errors import ErrorCode, MCPError
from app.models.schemas import ValidateItemsInput, build_success_response
from app.services.erpnext_client import ERPNextClient
from app.services.tenant_router import check_agent_entitlement, resolve_tenant

router = APIRouter(prefix="/tools", tags=["Item Tools"])
AGENT_ID = "invoice-ocr-agent"
TOOL_NAME = "validate_items"


@router.post("/validate_items")
async def validate_items(input_data: ValidateItemsInput) -> dict:
    start = time.time()
    tenant = resolve_tenant(input_data.tenant_id)
    check_agent_entitlement(tenant, AGENT_ID)
    if not input_data.items:
        raise MCPError(ErrorCode.VALIDATION_ERROR, "No items provided for validation.")

    client = ERPNextClient(tenant)
    validated = []
    matched_count = 0

    for item in input_data.items:
        match = await _find_item(client, item.description)
        if match["matched"]:
            matched_count += 1
        validated.append(
            {
                "description": item.description,
                "matched": match["matched"],
                "erpnext_item_code": match["erpnext_item_code"],
                "erpnext_item_name": match["erpnext_item_name"],
                "item_group": match["item_group"],
                "match_confidence": match["match_confidence"],
                "suggestions": match.get("suggestions", []),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
        )

    data = {
        "total_items": len(input_data.items),
        "matched_count": matched_count,
        "unmatched_count": len(input_data.items) - matched_count,
        "items": validated,
    }
    return build_success_response(
        TOOL_NAME,
        input_data.tenant_id,
        data,
        int((time.time() - start) * 1000),
    )


async def _find_item(client: ERPNextClient, description: str) -> dict:
    rows = await client.list_resource(
        "Item",
        filters=[["item_name", "like", f"%{description.split()[0]}%"]],
        fields=["name", "item_code", "item_name", "item_group"],
        limit=3,
    )
    for row in rows:
        item_name = row.get("item_name", "")
        if description.lower() in item_name.lower() or item_name.lower() in description.lower():
            return {
                "matched": True,
                "erpnext_item_code": row.get("item_code", row.get("name", "")),
                "erpnext_item_name": item_name,
                "item_group": row.get("item_group", ""),
                "match_confidence": 0.9,
                "suggestions": [],
            }
    return {
        "matched": False,
        "erpnext_item_code": None,
        "erpnext_item_name": None,
        "item_group": None,
        "match_confidence": 0.0,
        "suggestions": [
            {
                "item_code": row.get("item_code", row.get("name", "")),
                "item_name": row.get("item_name", ""),
                "similarity_score": 0.65,
            }
            for row in rows
        ],
    }
