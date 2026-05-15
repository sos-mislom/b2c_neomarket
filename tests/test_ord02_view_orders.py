from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_orders_list_returns_own_orders_paginated() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/orders?limit=1&offset=0&status=DELIVERED",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["status"] == "DELIVERED"


def test_order_detail_shows_fixed_prices() -> None:
    order_id = stable_uuid("order:7001")

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/orders/{order_id}",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["unit_price"] > 0
    assert item["line_total"] == item["unit_price"] * item["quantity"]


def test_other_user_order_returns_404_not_403() -> None:
    other_order_id = stable_uuid("order:7101")

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/orders/{other_order_id}",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
        )

    assert response.status_code == 404
