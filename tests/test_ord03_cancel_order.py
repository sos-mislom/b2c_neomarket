from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.services as product_services
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderStatus
from app.seed import stable_uuid


def test_cancel_paid_order_transitions_to_cancelled() -> None:
    order_id = stable_uuid("order:7001")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
            json={"reason": "changed_mind"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CANCELLED"
    assert payload["buyer_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["subtotal"] == payload["total_amount"]


def test_unreserve_failure_transitions_to_cancel_pending(monkeypatch) -> None:
    user_id = "cancel-pending-user"
    sku_id = stable_uuid("sku:milk-oolong-creamy-100g")

    def fake_post(*args, **kwargs):
        raise product_services.httpx.ConnectError("b2b down")

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers={"X-User-Id": user_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        order_response = client.post(
            "/api/v1/orders",
            headers={"X-User-Id": user_id},
            json={"idempotency_key": "cancel-pending-order"},
        )

        monkeypatch.setenv("B2B_BASE_URL", "http://b2b:8000")
        get_settings.cache_clear()
        monkeypatch.setattr(product_services.httpx, "post", fake_post)
        try:
            response = client.post(
                f"/api/v1/orders/{order_response.json()['id']}/cancel",
                headers={"X-User-Id": user_id},
                json={"reason": "changed_mind"},
            )
        finally:
            get_settings.cache_clear()

    assert add_response.status_code in {200, 201}
    assert order_response.status_code == 201
    assert response.status_code == 200
    assert response.json()["status"] == "CANCEL_PENDING"


def test_cancel_assembling_order_returns_409() -> None:
    order_id = stable_uuid("order:7002")

    with SessionLocal() as session:
        order = session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        order.status = OrderStatus.ASSEMBLING
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
            json={"reason": "too_late"},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "CANCEL_NOT_ALLOWED"


def test_other_user_order_returns_404() -> None:
    order_id = stable_uuid("order:7101")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
            json={"reason": "not_mine"},
        )

    assert response.status_code == 404
