from __future__ import annotations

from fastapi.testclient import TestClient

import app.services as product_services
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Sku
from app.seed import stable_uuid
from conftest import make_auth_headers


def test_checkout_creates_paid_order_with_fixed_prices() -> None:
    sku_id = stable_uuid("sku:tieguanyin-classic-100g")
    user_id = "checkout-user-fixed-prices"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": sku_id, "quantity": 2},
        )
        response = client.post(
            "/api/v1/orders",
            headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-fixed-prices"},
            json={
                "address_id": "addr-checkout",
                "payment_method_id": "pm-card",
            },
        )

    assert add_response.status_code == 200
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "PAID"
    assert payload["buyer_id"] == user_id
    assert payload["subtotal"] == payload["total_amount"]
    assert payload["total"] == payload["total_amount"]
    assert payload["address"]["id"] == "demo-address"
    item = next(item for item in payload["items"] if item["sku_id"] == sku_id)
    assert item["name"]
    assert item["unit_price"] > 0
    assert item["line_total"] == item["unit_price"] * 2


def test_idempotency_returns_existing_order() -> None:
    sku_id = stable_uuid("sku:milk-oolong-creamy-100g")
    user_id = "checkout-user-idempotent"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": sku_id, "quantity": 1},
        )
        first = client.post(
            "/api/v1/orders",
            headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-idempotent-key"},
            json={},
        )
        second = client.post(
            "/api/v1/orders",
            headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-idempotent-key"},
            json={},
        )

    assert add_response.status_code == 200
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


def test_checkout_calls_b2b_reserve_without_local_deduction(monkeypatch) -> None:
    sku_id = stable_uuid("sku:darjeeling-first-flush-100g")
    user_id = "checkout-user-b2b-reserve"
    calls = []

    with SessionLocal() as session:
        before_quantity = session.get(Sku, sku_id).active_quantity

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return product_services.httpx.Response(200, json={"reserved": True})

    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    monkeypatch.setenv("B2B_SERVICE_KEY", "secret-b2c-to-b2b")
    get_settings.cache_clear()
    monkeypatch.setattr(product_services.httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            add_response = client.post(
                "/api/v1/cart/items",
                headers=make_auth_headers(user_id),
                json={"sku_id": sku_id, "quantity": 1},
            )
            response = client.post(
                "/api/v1/orders",
                headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-b2b-reserve"},
                json={},
            )
    finally:
        get_settings.cache_clear()

    with SessionLocal() as session:
        after_quantity = session.get(Sku, sku_id).active_quantity

    assert add_response.status_code == 200
    assert response.status_code == 201
    assert calls[0]["url"] == "http://b2b:8000/api/v1/reserve"
    assert calls[0]["headers"]["X-Service-Key"] == "secret-b2c-to-b2b"
    assert calls[0]["json"] == {
        "idempotency_key": "checkout-b2b-reserve",
        "items": [{"sku_id": sku_id, "quantity": 1}],
    }
    assert after_quantity == before_quantity


def test_partial_reserve_failure_returns_409(monkeypatch) -> None:
    sku_id = stable_uuid("sku:tieguanyin-classic-50g")
    user_id = "checkout-user-partial-reserve"

    def fake_post(*args, **kwargs):
        return product_services.httpx.Response(409, json={"code": "INSUFFICIENT_STOCK"})

    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    get_settings.cache_clear()
    monkeypatch.setattr(product_services.httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            add_response = client.post(
                "/api/v1/cart/items",
                headers=make_auth_headers(user_id),
                json={"sku_id": sku_id, "quantity": 1},
            )
            response = client.post(
                "/api/v1/orders",
                headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-partial-reserve-failure"},
                json={},
            )
    finally:
        get_settings.cache_clear()

    assert add_response.status_code == 200
    assert response.status_code == 409
    assert response.json()["code"] == "RESERVE_FAILED"


def test_b2b_unavailable_returns_503(monkeypatch) -> None:
    sku_id = stable_uuid("sku:milk-oolong-creamy-250g")
    user_id = "checkout-user-b2b-unavailable"

    def fake_post(*args, **kwargs):
        raise product_services.httpx.ConnectError("b2b down")

    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    get_settings.cache_clear()
    monkeypatch.setattr(product_services.httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            add_response = client.post(
                "/api/v1/cart/items",
                headers=make_auth_headers(user_id),
                json={"sku_id": sku_id, "quantity": 1},
            )
            response = client.post(
                "/api/v1/orders",
                headers={**make_auth_headers(user_id), "Idempotency-Key": "checkout-b2b-unavailable"},
                json={},
            )
    finally:
        get_settings.cache_clear()

    assert add_response.status_code == 200
    assert response.status_code == 503
    assert response.json()["code"] == "B2B_UNAVAILABLE"

