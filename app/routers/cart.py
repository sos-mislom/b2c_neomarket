from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..errors import APIError
from ..models import CartItem, Order
from ..schemas import AddCartItemRequest, UpdateCartItemRequest
from ..services import (
    add_or_update_cart_item,
    build_cart_payload,
    build_validation_response,
    ensure_cart_item_owner,
    find_cart_item,
    get_cart_items,
    get_product_or_404,
    load_all_products,
    merge_guest_cart_into_user,
    product_is_visible,
    require_cart_identity,
    require_user_id,
    update_cart_item_quantity,
)


router = APIRouter(tags=["cart"])


@router.get("/api/v1/cart")
def get_cart(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    merge_guest_cart_into_user(session, user_id, session_id)
    return build_cart_payload(get_cart_items(session, user_id, session_id))


@router.delete("/api/v1/cart", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> Response:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    stmt = delete(CartItem)
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    else:
        stmt = stmt.where(CartItem.session_id == session_id)
    session.execute(stmt)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/cart/items")
def add_cart_item(
    payload: AddCartItemRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> JSONResponse:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    merge_guest_cart_into_user(session, user_id, session_id)
    item, status_code = add_or_update_cart_item(session, payload.sku_id, payload.quantity, user_id, session_id)
    cart_payload = build_cart_payload(get_cart_items(session, user_id, session_id))
    content = {
        "message": "Позиция корзины успешно обновлена" if status_code == 200 else "Товар добавлен в корзину",
        "item": next(entry for entry in cart_payload["items"] if entry["item_id"] == item.id),
        "summary": cart_payload["summary"],
    }
    return JSONResponse(status_code=status_code, content=content)


@router.get("/api/v1/cart/items/{item_id}")
def get_cart_item(
    item_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    item = ensure_cart_item_owner(find_cart_item(session, item_id), user_id, session_id)
    return next(entry for entry in build_cart_payload([item])["items"] if entry["item_id"] == item.id)


@router.put("/api/v1/cart/items/{item_id}")
def update_cart_item(
    item_id: str,
    payload: UpdateCartItemRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    item = ensure_cart_item_owner(find_cart_item(session, item_id), user_id, session_id)
    updated = update_cart_item_quantity(session, item, payload.quantity)
    cart_payload = build_cart_payload(get_cart_items(session, user_id, session_id))
    return {
        "message": "Позиция корзины успешно обновлена",
        "item": next(entry for entry in cart_payload["items"] if entry["item_id"] == updated.id),
        "summary": cart_payload["summary"],
    }


@router.delete("/api/v1/cart/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    item_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> Response:
    user_id, session_id = require_cart_identity(x_user_id, x_session_id)
    item = ensure_cart_item_owner(find_cart_item(session, item_id), user_id, session_id)
    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cart/validate")
@router.get("/api/v1/cart/validate")
def validate_cart(
    cart_item_ids: list[str] | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    items = get_cart_items(session, user_id, None)
    return build_validation_response(items, cart_item_ids)


@router.get("/api/v1/cart/also_bought")
def get_also_bought(
    limit: int = Query(default=10, ge=1, le=50),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    cart_items = get_cart_items(session, user_id, None)
    if not cart_items:
        raise APIError(409, "EMPTY_CART", "Cannot generate recommendations for empty cart")
    cart_product_ids = {item.sku.product_id for item in cart_items}
    orders = list(session.scalars(select(Order).options(selectinload(Order.items)).where(Order.user_id != user_id)).all())
    counter: Counter[str] = Counter()
    for order in orders:
        ordered_product_ids = {item.product_id for item in order.items}
        if ordered_product_ids.intersection(cart_product_ids):
            for product_id in ordered_product_ids - cart_product_ids:
                product = get_product_or_404(session, product_id)
                if product_is_visible(product):
                    counter[product_id] += 1
    return {"recommended_product_ids": [product_id for product_id, _ in counter.most_common(limit)]}
