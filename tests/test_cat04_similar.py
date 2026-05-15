from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_similar_returns_up_to_8_from_same_category() -> None:
    product_id = stable_uuid("product:sencha-yabukita-premium")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products/{product_id}/similar")

    assert response.status_code == 200
    payload = response.json()
    assert 0 < len(payload["items"]) <= 8
    assert product_id not in {item["id"] for item in payload["items"]}


def test_empty_category_returns_200_empty_list() -> None:
    product_id = stable_uuid("product:tea-box-evening-ritual")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/products/{product_id}/similar?limit=8")

    assert response.status_code == 200
    assert "items" in response.json()


def test_unknown_product_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products/not-a-product/similar")

    assert response.status_code == 404
