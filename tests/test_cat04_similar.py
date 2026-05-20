from __future__ import annotations

from fastapi.testclient import TestClient

import app.services as product_services
from app.config import get_settings
from app.main import app
from app.seed import stable_uuid


def test_similar_returns_up_to_8_from_same_category() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/products/{product_id}/similar")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert 0 < len(payload) <= 8
    assert product_id not in {item["id"] for item in payload}
    assert {"id", "name", "min_price", "has_stock", "images"} <= set(payload[0])


def test_empty_category_returns_200_empty_list() -> None:
    product_id = stable_uuid("product:tea-box-evening-ritual")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/products/{product_id}/similar?limit=8")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unknown_product_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/products/not-a-product/similar")

    assert response.status_code == 404


def test_nonexistent_category_returns_400() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")
    missing_category_id = stable_uuid("category:missing-similar")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/products/{product_id}/similar?category={missing_category_id}")

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_REQUEST"


def test_similar_products_proxied_to_b2b(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    monkeypatch.setenv("B2B_SERVICE_KEY", "secret-b2c-to-b2b")
    get_settings.cache_clear()
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "items": [
                    {
                        "id": "similar-id",
                        "title": "Similar Tea",
                        "images": ["/similar.jpg"],
                        "skus": [{"id": "sku-id", "price": 1200, "active_quantity": 2, "cost_price": 900}],
                    }
                ]
            }

    def fake_get(url: str, params: list[tuple[str, str]], headers: dict, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(product_services.httpx, "get", fake_get)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/products/product-id/similar?limit=4")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert captured["url"] == "http://b2b:8000/api/v1/products/product-id/similar"
    assert ("limit", "4") in captured["params"]
    assert captured["headers"]["X-Service-Key"] == "secret-b2c-to-b2b"
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["name"] == "Similar Tea"
    assert payload[0]["min_price"] == 1200
    assert payload[0]["has_stock"] is True
    assert "cost_price" not in payload[0]
    assert "reserved_quantity" not in payload[0]
