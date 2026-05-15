from __future__ import annotations

from fastapi.testclient import TestClient

import app.services as product_services
from app.config import get_settings
from app.main import app
from app.seed import stable_uuid


def test_delivered_status_triggers_fulfill_to_b2b(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    get_settings.cache_clear()
    captured = {}

    class FakeResponse:
        status_code = 200

    def fake_post(url: str, json: dict, headers: dict, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(product_services.httpx, "post", fake_post)
    order_id = stable_uuid("order:7103")

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/orders/{order_id}/deliver",
                headers={"X-Service-Key": "secret-b2c-to-b2b"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"
    assert response.json()["fulfill_sent"] is True
    assert captured["url"] == "http://b2b:8000/api/v1/fulfill"
    assert captured["json"]["order_id"] == order_id
    assert captured["json"]["items"]


def test_fulfill_failure_retried_asynchronously_scaffold(monkeypatch) -> None:
    monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
    get_settings.cache_clear()

    def fake_post(*args, **kwargs):
        raise product_services.httpx.ConnectError("b2b down")

    monkeypatch.setattr(product_services.httpx, "post", fake_post)
    order_id = stable_uuid("order:7102")

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/orders/{order_id}/deliver",
                headers={"X-Service-Key": "secret-b2c-to-b2b"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"
    assert response.json()["fulfill_sent"] is False
