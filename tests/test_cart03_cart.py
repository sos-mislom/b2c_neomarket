from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import CartItem
from app.seed import stable_uuid


def test_add_sku_increments_quantity_if_already_in_cart() -> None:
    sku_id = stable_uuid("sku:assam-gold-breakfast-250g")
    session_id = "cart-session-increment"

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/cart/items",
            headers={"X-Session-Id": session_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        second = client.post(
            "/api/v1/cart/items",
            headers={"X-Session-Id": session_id},
            json={"sku_id": sku_id, "quantity": 1},
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["item"]["quantity"] == 2


def test_get_cart_enriched_with_b2b_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/cart", headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert "product_title" in payload["items"][0]
    assert "unit_price" in payload["items"][0]
    assert payload["summary"]["currency"] == "RUB"


def test_unavailable_sku_shown_with_reason() -> None:
    blocked_sku_id = stable_uuid("sku:tea-sampler-weekend-market-6x25")

    with TestClient(app) as client:
        response = client.get("/api/v1/cart", headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"})

    assert response.status_code == 200
    item = next(item for item in response.json()["items"] if item["sku_id"] == blocked_sku_id)
    assert item["available"] is False
    assert item["unavailable_reason"] == "PRODUCT_BLOCKED"


def test_guest_cart_merged_on_login() -> None:
    sku_id = stable_uuid("sku:earl-grey-bergamot-100g")
    user_id = "merge-cart-user"
    session_id = "merge-cart-session"

    with TestClient(app) as client:
        guest = client.post(
            "/api/v1/cart/items",
            headers={"X-Session-Id": session_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        authed = client.post(
            "/api/v1/cart/items",
            headers={"X-User-Id": user_id},
            json={"sku_id": sku_id, "quantity": 3},
        )
        merged = client.get("/api/v1/cart", headers={"X-User-Id": user_id, "X-Session-Id": session_id})

    assert guest.status_code == 201
    assert authed.status_code == 201
    assert merged.status_code == 200
    items = [item for item in merged.json()["items"] if item["sku_id"] == sku_id]
    assert len(items) == 1
    assert items[0]["quantity"] == 3

    with SessionLocal() as session:
        guest_leftovers = list(session.scalars(select(CartItem).where(CartItem.session_id == session_id)).all())
    assert guest_leftovers == []
