"""Pydantic schemas and standard MCP response helpers."""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MCPMetadata(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    execution_time_ms: int = 0


class MCPErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[str] = None
    recoverable: bool = False


class MCPResponse(BaseModel):
    success: bool
    tool: str
    tenant_id: str
    data: Optional[dict[str, Any]] = None
    error: Optional[MCPErrorDetail] = None
    metadata: MCPMetadata = Field(default_factory=MCPMetadata)


class ProcessOCRDocumentInput(BaseModel):
    tenant_id: str
    image_data: str
    document_type: str = "invoice"
    language: str = "auto"
    vendor_id: Optional[str] = None


class ValidateSupplierInput(BaseModel):
    tenant_id: str
    supplier_name: str


class ItemToValidate(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None


class ValidateItemsInput(BaseModel):
    tenant_id: str
    items: list[ItemToValidate]


class InvoiceLineItem(BaseModel):
    description: str
    item_code: Optional[str] = None
    quantity: float
    unit_price: float
    total_price: Optional[float] = None


class CreatePurchaseInvoiceInput(BaseModel):
    tenant_id: str
    supplier_name: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str] = None
    currency: str = "EUR"
    line_items: list[InvoiceLineItem]
    total_net: float
    total_vat: float
    total_gross: float
    vat_rate: float
    confirmed: bool


def build_success_response(
    tool: str,
    tenant_id: str,
    data: dict[str, Any],
    execution_time_ms: int = 0,
) -> dict:
    return MCPResponse(
        success=True,
        tool=tool,
        tenant_id=tenant_id,
        data=data,
        metadata=MCPMetadata(execution_time_ms=execution_time_ms),
    ).model_dump()


def build_error_response(
    tool: str,
    tenant_id: str,
    code: str,
    message: str,
    details: Optional[str] = None,
    recoverable: bool = False,
    execution_time_ms: int = 0,
) -> dict:
    return MCPResponse(
        success=False,
        tool=tool,
        tenant_id=tenant_id,
        error=MCPErrorDetail(
            code=code,
            message=message,
            details=details,
            recoverable=recoverable,
        ),
        metadata=MCPMetadata(execution_time_ms=execution_time_ms),
    ).model_dump()
