from tests.conftest import INVALID_TENANT_ID, VALID_TENANT_ID


def test_validate_supplier_rejects_empty_name(client):
    response = client.post(
        "/tools/validate_supplier",
        json={"tenant_id": VALID_TENANT_ID, "supplier_name": ""},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validate_supplier_rejects_invalid_tenant(client):
    response = client.post(
        "/tools/validate_supplier",
        json={"tenant_id": INVALID_TENANT_ID, "supplier_name": "Test"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TENANT_ERROR"


def test_validate_items_rejects_empty_list(client):
    response = client.post(
        "/tools/validate_items",
        json={"tenant_id": VALID_TENANT_ID, "items": []},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validate_items_rejects_invalid_tenant(client):
    response = client.post(
        "/tools/validate_items",
        json={"tenant_id": INVALID_TENANT_ID, "items": [{"description": "Rosen"}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TENANT_ERROR"
