from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_cat01.sqlite"
os.environ["AUTO_SEED"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB = Path("test_cat01.sqlite")
if TEST_DB.exists():
    TEST_DB.unlink()

import httpx
from fastapi.testclient import TestClient

import app.services as product_services
from app.config import get_settings
from app.main import app
from app.seed import stable_uuid


def test_catalog_returns_filtered_sorted_products() -> None:
    category_id = stable_uuid("category:green-tea")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products?category_id={category_id}&sort=price_asc&limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 3
    prices = [item["price"] for item in payload["items"]]
    assert prices == sorted(prices)
    assert stable_uuid("product:tea-sampler-weekend-market") not in {item["id"] for item in payload["items"]}
    assert all(item["in_stock"] is True for item in payload["items"])


def test_facets_return_counts_per_filter_value() -> None:
    category_id = stable_uuid("category:green-tea")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/facets?category_id={category_id}")

    assert response.status_code == 200
    facets = response.json()["facets"]
    brand_facet = next(item for item in facets if item["name"] == "brand")
    assert any(value["value"] == "Shizuoka Leaf" and value["count"] == 1 for value in brand_facet["values"])


def test_invalid_sort_returns_400() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products?sort=totally_wrong")

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_SORT"
    assert "price_asc" in payload["message"]


def test_b2b_unavailable_returns_503(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    monkeypatch.setenv("B2B_SERVICE_KEY", "secret-b2c-to-b2b")
    get_settings.cache_clear()

    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("b2b is down")

    monkeypatch.setattr(product_services.httpx, "get", fake_get)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products?limit=10")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["code"] == "B2B_UNAVAILABLE"


def test_b2b_catalog_response_is_sanitized_and_authorized(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    monkeypatch.setenv("B2B_SERVICE_KEY", "secret-b2c-to-b2b")
    monkeypatch.setenv("B2B_AUTH_TOKEN", "seller-token")
    get_settings.cache_clear()
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "total_count": 1,
                "limit": 10,
                "offset": 0,
                "items": [
                    {
                        "id": "product-id",
                        "title": "Tea",
                        "description": "Green tea",
                        "status": "MODERATED",
                        "images": ["/image.jpg"],
                        "skus": [
                            {
                                "id": "sku-id",
                                "name": "50g",
                                "price": 1000,
                                "cost_price": 700,
                                "quantity": 3,
                                "reserved_quantity": 1,
                            }
                        ],
                    }
                ],
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
            response = client.get("/api/v1/products?limit=10&sort=price_asc")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert captured["url"] == "http://b2b:8000/api/v1/products"
    assert ("sort", "price_asc") in captured["params"]
    assert captured["headers"]["X-Service-Key"] == "secret-b2c-to-b2b"
    assert captured["headers"]["Authorization"] == "Bearer seller-token"
    item = response.json()["items"][0]
    assert item["images"] == [{"url": "/image.jpg", "ordering": 0}]
    assert item["skus"][0]["active_quantity"] == 3
    assert item["skus"][0]["in_stock"] is True
    assert "cost_price" not in item["skus"][0]
    assert "reserved_quantity" not in item["skus"][0]
