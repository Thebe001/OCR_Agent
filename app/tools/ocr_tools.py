"""OCR tool endpoint."""

import base64
import time

from fastapi import APIRouter

from app.models.errors import ErrorCode, MCPError
from app.models.schemas import ProcessOCRDocumentInput, build_success_response
from app.services.ocr_service import create_ocr_service
from app.services.tenant_router import check_agent_entitlement, resolve_tenant

router = APIRouter(prefix="/tools", tags=["OCR Tools"])
AGENT_ID = "invoice-ocr-agent"
TOOL_NAME = "process_ocr_document"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.post("/process_ocr_document")
async def process_ocr_document(input_data: ProcessOCRDocumentInput) -> dict:
    start = time.time()
    tenant = resolve_tenant(input_data.tenant_id)
    check_agent_entitlement(tenant, AGENT_ID)

    if input_data.document_type != "invoice":
        raise MCPError(ErrorCode.VALIDATION_ERROR, "I can only process supplier invoices.")
    if input_data.language not in {"de", "en", "auto"}:
        raise MCPError(ErrorCode.VALIDATION_ERROR, "Unsupported document language.")
    if not input_data.image_data or not input_data.image_data.strip():
        raise MCPError(ErrorCode.VALIDATION_ERROR, "No image data provided. Please upload an invoice image.")

    try:
        decoded = base64.b64decode(input_data.image_data, validate=True)
    except Exception as exc:
        raise MCPError(
            ErrorCode.VALIDATION_ERROR,
            "The uploaded file could not be read. Please upload a valid image or PDF.",
            details=str(exc),
        ) from exc

    if len(decoded) > MAX_IMAGE_BYTES:
        raise MCPError(
            ErrorCode.VALIDATION_ERROR,
            "The uploaded file is too large. Please keep images and PDFs under 10 MB.",
        )

    result = await create_ocr_service().extract_invoice_data(
        input_data.image_data,
        input_data.language,
        input_data.vendor_id,
    )
    return build_success_response(
        TOOL_NAME,
        input_data.tenant_id,
        result,
        int((time.time() - start) * 1000),
    )
