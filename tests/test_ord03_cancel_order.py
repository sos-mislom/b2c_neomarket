from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

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
    assert response.json()["status"] == "CANCELLED"


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
