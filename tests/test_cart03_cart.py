from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import CartItem, Product, Sku
from app.seed import stable_uuid
from conftest import make_auth_headers


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

    assert first.status_code == 200
    assert second.status_code == 200
    item = next(item for item in second.json()["items"] if item["sku_id"] == sku_id)
    assert item["quantity"] == 2
    assert {"items", "items_count", "subtotal", "is_valid"} <= set(second.json())


def test_get_cart_enriched_with_b2b_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/cart", headers=make_auth_headers("11111111-1111-1111-1111-111111111111"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert "product_title" in payload["items"][0]
    assert "name" in payload["items"][0]
    assert "unit_price" in payload["items"][0]
    assert "available_quantity" in payload["items"][0]
    assert "is_available" in payload["items"][0]
    assert {"id", "url", "ordering"} <= set(payload["items"][0]["image"])
    assert payload["summary"]["currency"] == "RUB"
    assert "subtotal" in payload


def test_unavailable_sku_shown_with_reason() -> None:
    blocked_sku_id = stable_uuid("sku:tea-sampler-weekend-market-6x25")

    with TestClient(app) as client:
        response = client.get("/api/v1/cart", headers=make_auth_headers("11111111-1111-1111-1111-111111111111"))

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
            headers=make_auth_headers(user_id),
            json={"sku_id": sku_id, "quantity": 3},
        )
        merged = client.get("/api/v1/cart", headers={**make_auth_headers(user_id), "X-Session-Id": session_id})

    assert guest.status_code == 200
    assert authed.status_code == 200
    assert merged.status_code == 200
    items = [item for item in merged.json()["items"] if item["sku_id"] == sku_id]
    assert len(items) == 1
    assert items[0]["quantity"] == 3

    with SessionLocal() as session:
        guest_leftovers = list(session.scalars(select(CartItem).where(CartItem.session_id == session_id)).all())
    assert guest_leftovers == []


def test_explicit_cart_merge_endpoint_returns_cart_response() -> None:
    sku_id = stable_uuid("sku:earl-grey-bergamot-100g")
    user_id = "merge-endpoint-user"
    session_id = "merge-endpoint-session"

    with TestClient(app) as client:
        guest = client.post(
            "/api/v1/cart/items",
            headers={"X-Session-Id": session_id},
            json={"sku_id": sku_id, "quantity": 2},
        )
        merged = client.post("/api/v1/cart/merge", headers={**make_auth_headers(user_id), "X-Session-Id": session_id})

    assert guest.status_code == 200
    assert merged.status_code == 200
    assert next(item for item in merged.json()["items"] if item["sku_id"] == sku_id)["quantity"] == 2


def test_patch_and_delete_cart_item_by_sku_id_return_cart_response() -> None:
    sku_id = stable_uuid("sku:earl-grey-bergamot-100g")
    session_id = "cart-session-sku-path"

    with TestClient(app) as client:
        client.post(
            "/api/v1/cart/items",
            headers={"X-Session-Id": session_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        patched = client.patch(
            f"/api/v1/cart/items/{sku_id}",
            headers={"X-Session-Id": session_id},
            json={"quantity": 2},
        )
        deleted = client.delete(f"/api/v1/cart/items/{sku_id}", headers={"X-Session-Id": session_id})

    assert patched.status_code == 200
    assert next(item for item in patched.json()["items"] if item["sku_id"] == sku_id)["quantity"] == 2
    assert deleted.status_code == 200
    assert deleted.json()["items"] == []


def test_cart_validate_supports_protocol_post() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/cart/validate", headers=make_auth_headers("11111111-1111-1111-1111-111111111111"))

    assert response.status_code == 200
    assert "is_valid" in response.json()


def test_cart_validate_response_matches_contract_with_issues() -> None:
    user_id = "cart-validate-contract-user"
    deleted_sku_id = stable_uuid("sku:darjeeling-first-flush-50g")
    deleted_product_id = stable_uuid("product:darjeeling-first-flush")
    out_of_stock_sku_id = stable_uuid("sku:milk-oolong-creamy-100g")
    allowed_issue_types = {
        "PRICE_CHANGED",
        "OUT_OF_STOCK",
        "QUANTITY_REDUCED",
        "PRODUCT_BLOCKED",
        "PRODUCT_DELETED",
    }

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": deleted_sku_id, "quantity": 1},
        )
        second = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers(user_id),
            json={"sku_id": out_of_stock_sku_id, "quantity": 1},
        )

        with SessionLocal() as session:
            deleted_product = session.get(Product, deleted_product_id)
            out_of_stock_sku = session.get(Sku, out_of_stock_sku_id)
            assert deleted_product is not None
            assert out_of_stock_sku is not None
            original_deleted = deleted_product.is_deleted
            original_quantity = out_of_stock_sku.active_quantity
            deleted_product.is_deleted = True
            out_of_stock_sku.active_quantity = 0
            session.commit()

        try:
            response = client.post("/api/v1/cart/validate", headers=make_auth_headers(user_id))
        finally:
            with SessionLocal() as session:
                deleted_product = session.get(Product, deleted_product_id)
                out_of_stock_sku = session.get(Sku, out_of_stock_sku_id)
                if deleted_product is not None:
                    deleted_product.is_deleted = original_deleted
                if out_of_stock_sku is not None:
                    out_of_stock_sku.active_quantity = original_quantity
                session.commit()

    assert first.status_code == 200
    assert second.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert {"is_valid", "cart", "issues"} <= set(payload)
    assert {"items", "items_count", "subtotal", "is_valid"} <= set(payload["cart"])
    assert payload["is_valid"] is False
    assert {issue["type"] for issue in payload["issues"]} >= {"PRODUCT_DELETED", "OUT_OF_STOCK"}
    for issue in payload["issues"]:
        assert {"sku_id", "type", "message"} <= set(issue)
        assert "issue_type" not in issue
        assert issue["type"] in allowed_issue_types


def test_cart_uses_jwt_claim_not_x_user_id_header() -> None:
    sku_id = stable_uuid("sku:earl-grey-bergamot-100g")
    jwt_user_id = "jwt-cart-owner"
    spoofed_user_id = "spoofed-cart-owner"

    with TestClient(app) as client:
        add_response = client.post(
            "/api/v1/cart/items",
            headers={**make_auth_headers(jwt_user_id), "X-User-Id": spoofed_user_id},
            json={"sku_id": sku_id, "quantity": 1},
        )
        jwt_cart = client.get("/api/v1/cart", headers=make_auth_headers(jwt_user_id))
        spoofed_cart = client.get("/api/v1/cart", headers=make_auth_headers(spoofed_user_id))

    assert add_response.status_code == 200
    assert any(item["sku_id"] == sku_id for item in jwt_cart.json()["items"])
    assert all(item["sku_id"] != sku_id for item in spoofed_cart.json()["items"])


def test_add_unavailable_sku_returns_404() -> None:
    blocked_sku_id = stable_uuid("sku:tea-sampler-weekend-market-6x25")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cart/items",
            headers=make_auth_headers("unavailable-sku-user"),
            json={"sku_id": blocked_sku_id, "quantity": 1},
        )

    assert response.status_code == 404
