from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_collections_list_returns_metadata_without_products() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/main/collections")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["total_count"] >= 1
    assert "products" not in payload["collections"][0]


def test_catalog_collections_return_protocol_array() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload
    assert {"id", "name", "products"} <= set(payload[0])
    assert payload[0]["products"]
    product = payload[0]["products"][0]
    assert {"id", "name", "min_price", "has_stock", "images"} <= set(product)
    assert "title" not in product
    assert "price_from" not in product
    assert isinstance(product["min_price"], int)
    assert isinstance(product["has_stock"], bool)
    assert isinstance(product["images"], list)


def test_collection_products_enriched_from_b2b() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/collections/green-harvest/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    product = payload["items"][0]
    assert {"id", "name", "min_price", "has_stock", "images"} <= set(product)
    assert "title" not in product
    assert "price_from" not in product
    assert isinstance(product["min_price"], int)
    assert isinstance(product["has_stock"], bool)
    assert isinstance(product["images"], list)
    assert product["skus"]


def test_unavailable_products_in_unavailable_ids() -> None:
    blocked_product_id = stable_uuid("product:tea-sampler-weekend-market")

    with TestClient(app) as client:
        response = client.get("/api/v1/collections/gift-boxes/products")

    assert response.status_code == 200
    assert blocked_product_id in response.json()["unavailable_ids"]


def test_unknown_collection_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/collections/unknown/products")

    assert response.status_code == 404
