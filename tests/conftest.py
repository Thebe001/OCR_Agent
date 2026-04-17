import base64

import fitz
import pytest
from fastapi.testclient import TestClient

from app.config.tenants import TenantConfig, register_tenant
from app.main import app

VALID_TENANT_ID = "test-florist-001"
INVALID_TENANT_ID = "missing-tenant-999"
def _build_invoice_pdf_base64() -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Blumen Grosshandel GmbH\nRechnung INV-2026-0042\nDatum: 08.04.2026\nFaellig: 22.04.2026\nNetto 94,00 EUR\nMwSt 7% 6,58 EUR\nBrutto 100,58 EUR\nRote Rosen 50 1,20 EUR 60,00 EUR")
    pdf_bytes = doc.tobytes()
    doc.close()
    return base64.b64encode(pdf_bytes).decode()


FAKE_IMAGE_DATA = _build_invoice_pdf_base64()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_tenant():
    register_tenant(
        TenantConfig(
            tenant_id=VALID_TENANT_ID,
            site_url="http://localhost:8080",
            api_key="test-api-key",
            api_secret="test-api-secret",
            subscription_tier="pro",
            active_agents=["invoice-ocr-agent"],
        )
    )


VALID_OCR_REQUEST = {
    "tenant_id": VALID_TENANT_ID,
    "image_data": FAKE_IMAGE_DATA,
    "document_type": "invoice",
    "language": "de",
}

VALID_INVOICE_REQUEST = {
    "tenant_id": VALID_TENANT_ID,
    "supplier_name": "Blumen Grosshandel GmbH",
    "invoice_number": "INV-2026-0042",
    "invoice_date": "2026-04-08",
    "due_date": "2026-04-22",
    "currency": "EUR",
    "line_items": [
        {"description": "Rote Rosen", "quantity": 50, "unit_price": 1.2, "total_price": 60.0}
    ],
    "total_net": 60.0,
    "total_vat": 4.2,
    "total_gross": 64.2,
    "vat_rate": 7,
    "confirmed": True,
}
