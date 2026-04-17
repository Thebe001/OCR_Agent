from tests.conftest import INVALID_TENANT_ID, VALID_INVOICE_REQUEST


def test_create_invoice_requires_confirmation(client):
    request = {**VALID_INVOICE_REQUEST, "confirmed": False}
    response = client.post("/tools/create_purchase_invoice", json=request)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_invoice_rejects_bad_totals(client):
    request = {**VALID_INVOICE_REQUEST, "total_gross": 99.99}
    response = client.post("/tools/create_purchase_invoice", json=request)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_invoice_rejects_bad_vat_rate(client):
    request = {**VALID_INVOICE_REQUEST, "vat_rate": 15}
    response = client.post("/tools/create_purchase_invoice", json=request)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_invoice_rejects_invalid_tenant(client):
    request = {**VALID_INVOICE_REQUEST, "tenant_id": INVALID_TENANT_ID}
    response = client.post("/tools/create_purchase_invoice", json=request)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TENANT_ERROR"


def test_create_invoice_rejects_invalid_date_format(client):
    request = {**VALID_INVOICE_REQUEST, "invoice_date": "not-a-date"}
    response = client.post("/tools/create_purchase_invoice", json=request)
    assert response.status_code == 422


def test_create_invoice_valid_data_reaches_erpnext(client):
    response = client.post("/tools/create_purchase_invoice", json=VALID_INVOICE_REQUEST)
    assert response.status_code in {200, 502}
    if response.status_code == 502:
        assert response.json()["error"]["code"] == "ERPNEXT_ERROR"
