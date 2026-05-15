from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_subscribe_returns_201_with_notify_on() -> None:
    product_id = stable_uuid("product:longjing-spring-reserve")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": "subscription-user"},
            json={"notify_on": ["PRICE_DOWN", "IN_STOCK"]},
        )

    assert response.status_code == 201
    assert response.json()["notify_on"] == ["PRICE_DOWN", "IN_STOCK"]


def test_duplicate_subscription_returns_409() -> None:
    product_id = stable_uuid("product:darjeeling-first-flush")
    user_id = "duplicate-subscription-user"

    with TestClient(app) as client:
        first = client.post(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": user_id},
            json={"notify_on": ["IN_STOCK"]},
        )
        second = client.post(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": user_id},
            json={"notify_on": ["IN_STOCK"]},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "SUBSCRIPTION_ALREADY_EXISTS"


def test_invalid_notify_on_returns_422() -> None:
    product_id = stable_uuid("product:darjeeling-first-flush")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": "invalid-subscription-user"},
            json={"notify_on": []},
        )

    assert response.status_code == 422


def test_unsubscribe_is_idempotent() -> None:
    product_id = stable_uuid("product:gyokuro-asahi-shade")

    with TestClient(app) as client:
        first = client.delete(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
        )
        second = client.delete(
            f"/api/v1/favorites/{product_id}/subscribe",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
        )

    assert first.status_code == 204
    assert second.status_code == 204
