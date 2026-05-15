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


def test_collection_products_enriched_from_b2b() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/collections/green-harvest/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert "price_from" in payload["items"][0]
    assert payload["items"][0]["skus"]


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
