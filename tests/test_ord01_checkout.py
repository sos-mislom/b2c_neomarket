from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_checkout_creates_paid_order_with_fixed_prices() -> None:
    sku_id = stable_uuid("sku:tieguanyin-classic-100g")
    user_id = "checkout-user-fixed-prices"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers={"X-User-Id": user_id},
            json={"sku_id": sku_id, "quantity": 2},
        )
        response = client.post(
            "/api/v1/orders",
            headers={"X-User-Id": user_id},
            json={"idempotency_key": "checkout-fixed-prices"},
        )

    assert add_response.status_code == 201
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "PAID"
    item = next(item for item in payload["items"] if item["sku_id"] == sku_id)
    assert item["unit_price"] > 0
    assert item["line_total"] == item["unit_price"] * 2


def test_idempotency_returns_existing_order() -> None:
    sku_id = stable_uuid("sku:milk-oolong-creamy-100g")
    user_id = "checkout-user-idempotent"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers={"X-User-Id": user_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        first = client.post(
            "/api/v1/orders",
            headers={"X-User-Id": user_id},
            json={"idempotency_key": "checkout-idempotent-key"},
        )
        second = client.post(
            "/api/v1/orders",
            headers={"X-User-Id": user_id},
            json={"idempotency_key": "checkout-idempotent-key"},
        )

    assert add_response.status_code == 201
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
