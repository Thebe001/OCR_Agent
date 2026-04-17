from tests.conftest import INVALID_TENANT_ID, VALID_OCR_REQUEST


def test_process_ocr_document_success(client):
    response = client.post("/tools/process_ocr_document", json=VALID_OCR_REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["tool"] == "process_ocr_document"
    assert body["data"]["vendor_name"]
    assert 0 <= body["data"]["confidence_score"] <= 1


def test_process_ocr_document_rejects_empty_image(client):
    request = {**VALID_OCR_REQUEST, "image_data": ""}
    response = client.post("/tools/process_ocr_document", json=request)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_process_ocr_document_rejects_invalid_tenant(client):
    request = {**VALID_OCR_REQUEST, "tenant_id": INVALID_TENANT_ID}
    response = client.post("/tools/process_ocr_document", json=request)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "TENANT_ERROR"


def test_process_ocr_document_rejects_non_invoice(client):
    request = {**VALID_OCR_REQUEST, "document_type": "receipt"}
    response = client.post("/tools/process_ocr_document", json=request)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
