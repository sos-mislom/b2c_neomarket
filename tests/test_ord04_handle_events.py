from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid
from conftest import make_auth_headers


def test_product_blocked_marks_cart_items_unavailable() -> None:
    sku_id = stable_uuid("sku:darjeeling-first-flush-100g")
    user_id = "event-cart-user"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": sku_id, "quantity": 1},
        )
        event_response = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "secret-b2c-to-b2b"},
            json={"type": "PRODUCT_BLOCKED", "sku_ids": [sku_id], "idempotency_key": "product-blocked-event-key"},
        )
        cart_response = client.get("/api/v1/cart", headers=make_auth_headers(user_id))

    assert add_response.status_code == 200
    assert event_response.status_code == 200
    item = next(item for item in cart_response.json()["items"] if item["sku_id"] == sku_id)
    assert item["available"] is False
    assert item["unavailable_reason"] == "PRODUCT_BLOCKED"


def test_protocol_b2b_event_marks_product_skus_unavailable() -> None:
    sku_id = stable_uuid("sku:darjeeling-first-flush-100g")
    product_id = stable_uuid("product:darjeeling-first-flush")
    user_id = "protocol-event-cart-user"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": sku_id, "quantity": 1},
        )
        event_response = client.post(
            "/api/v1/b2b/events",
            headers={"X-Service-Key": "secret-b2c-to-b2b"},
            json={
                "event_type": "PRODUCT_BLOCKED",
                "idempotency_key": "protocol-product-blocked-event-key",
                "occurred_at": "2026-05-26T00:00:00Z",
                "payload": {"product_id": product_id, "reason": "moderation"},
            },
        )
        cart_response = client.get("/api/v1/cart", headers=make_auth_headers(user_id))

    assert add_response.status_code in {200, 201}
    assert event_response.status_code == 202
    item = next(item for item in cart_response.json()["items"] if item["sku_id"] == sku_id)
    assert item["available"] is False
    assert item["unavailable_reason"] == "PRODUCT_BLOCKED"


def test_orders_not_affected_by_product_blocked() -> None:
    order_id = stable_uuid("order:7001")
    sku_id = stable_uuid("sku:assam-gold-breakfast-100g")

    with TestClient(app) as client:
        before_response = client.get(
            f"/api/v1/orders/{order_id}",
            headers=make_auth_headers("11111111-1111-1111-1111-111111111111"),
        )
        event_response = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "secret-b2c-to-b2b"},
            json={"type": "PRODUCT_BLOCKED", "sku_ids": [sku_id], "idempotency_key": "order-not-affected-key"},
        )
        order_response = client.get(
            f"/api/v1/orders/{order_id}",
            headers=make_auth_headers("11111111-1111-1111-1111-111111111111"),
        )

    assert event_response.status_code == 200
    assert order_response.status_code == 200
    assert order_response.json()["status"] == before_response.json()["status"]


def test_idempotent_event_no_side_effects() -> None:
    sku_id = stable_uuid("sku:ivan-chai-taiga-100g")
    user_id = "event-idempotent-user"

    with TestClient(app) as client:
        client.post("/api/v1/cart/items", headers=make_auth_headers(user_id), json={"sku_id": sku_id, "quantity": 1})
        first = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "secret-b2c-to-b2b"},
            json={"type": "OUT_OF_STOCK", "sku_ids": [sku_id], "idempotency_key": "same-event-key"},
        )
        second = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "secret-b2c-to-b2b"},
            json={"type": "PRODUCT_DELETED", "sku_ids": [sku_id], "idempotency_key": "same-event-key"},
        )

    assert first.json() == {"processed": True, "updated": 1}
    assert second.json() == {"processed": False, "updated": 0}


def test_missing_service_key_returns_401() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events/product",
            json={"type": "PRODUCT_BLOCKED", "sku_ids": [stable_uuid("sku:darjeeling-first-flush-100g")], "idempotency_key": "missing-service-key"},
        )

    assert response.status_code == 401

