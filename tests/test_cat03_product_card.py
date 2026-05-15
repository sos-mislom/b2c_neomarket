from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.services as product_services
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Sku
from app.seed import stable_uuid


def test_product_card_returns_full_data_with_skus() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products/{product_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == product_id
    assert payload["title"]
    assert payload["description"]
    assert payload["images"]
    assert payload["characteristics"]
    assert payload["skus"]
    assert isinstance(payload["skus"][0]["price"], int)
    assert "discount" in payload["skus"][0]
    assert "active_quantity" in payload["skus"][0]
    assert "in_stock" in payload["skus"][0]


def test_cost_price_absent_in_response() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products/{product_id}")

    assert response.status_code == 200
    first_sku = response.json()["skus"][0]
    assert "cost_price" not in first_sku
    assert "reserved_quantity" not in first_sku


def test_blocked_product_returns_404() -> None:
    blocked_product_id = stable_uuid("product:tea-sampler-weekend-market")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products/{blocked_product_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


def test_sku_without_stock_is_shown_as_unavailable() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")
    sku_id = stable_uuid("sku:sencha-yabukita-premium-50g")

    with TestClient(app) as client:
        with SessionLocal() as session:
            sku = session.scalar(select(Sku).where(Sku.id == sku_id))
            assert sku is not None
            sku.active_quantity = 0
            session.commit()

        response = client.get(f"/api/v1/products/{product_id}")

    assert response.status_code == 200
    skus = response.json()["skus"]
    out_of_stock_sku = next(item for item in skus if item["id"] == sku_id)
    assert out_of_stock_sku["active_quantity"] == 0
    assert out_of_stock_sku["in_stock"] is False


def test_b2b_product_response_is_sanitized_and_authorized(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    monkeypatch.setenv("B2B_SERVICE_KEY", "secret-b2c-to-b2b")
    monkeypatch.setenv("B2B_AUTH_TOKEN", "seller-token")
    get_settings.cache_clear()
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "id": "product-id",
                "title": "Tea",
                "description": "Green tea",
                "status": "MODERATED",
                "deleted": False,
                "blocked": False,
                "category_id": "category-id",
                "images": [{"url": "/image.jpg", "ordering": 0}],
                "characteristics": [],
                "skus": [
                    {
                        "id": "sku-id",
                        "name": "50g",
                        "price": 1000,
                        "cost_price": 700,
                        "active_quantity": 3,
                        "reserved_quantity": 1,
                    }
                ],
            }

    def fake_get(url: str, headers: dict, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(product_services.httpx, "get", fake_get)

    try:
        payload = product_services.fetch_b2b_product_card("product-id")
    finally:
        get_settings.cache_clear()

    assert captured["url"] == "http://b2b:8000/api/v1/products/product-id"
    assert captured["headers"]["X-Service-Key"] == "secret-b2c-to-b2b"
    assert captured["headers"]["Authorization"] == "Bearer seller-token"
    assert payload["category_id"] == "category-id"
    assert "cost_price" not in payload["skus"][0]
    assert "reserved_quantity" not in payload["skus"][0]
