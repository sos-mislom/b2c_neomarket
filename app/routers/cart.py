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
    user_id_from_authorization,
    update_cart_item_quantity,
)


router = APIRouter(tags=["cart"])


def find_owned_cart_item_by_sku_or_id(session: Session, item_ref: str, user_id: str | None, session_id: str | None) -> CartItem:
    for item in get_cart_items(session, user_id, session_id):
        if item.sku_id == item_ref or item.id == item_ref:
            return item
    raise APIError(404, "CART_ITEM_NOT_FOUND", "Cart item not found")


@router.get("/api/v1/cart")
def get_cart(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
    merge_guest_cart_into_user(session, user_id, session_id)
    return build_cart_payload(get_cart_items(session, user_id, session_id))


@router.delete("/api/v1/cart", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> Response:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
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
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> JSONResponse:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
    merge_guest_cart_into_user(session, user_id, session_id)
    add_or_update_cart_item(session, payload.sku_id, payload.quantity, user_id, session_id)
    cart_payload = build_cart_payload(get_cart_items(session, user_id, session_id))
    return JSONResponse(status_code=status.HTTP_200_OK, content=cart_payload)


@router.get("/api/v1/cart/items/{item_id}")
def get_cart_item(
    item_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
    item = ensure_cart_item_owner(find_cart_item(session, item_id), user_id, session_id)
    return next(entry for entry in build_cart_payload([item])["items"] if entry["item_id"] == item.id)


@router.put("/api/v1/cart/items/{item_id}")
@router.patch("/api/v1/cart/items/{item_id}")
def update_cart_item(
    item_id: str,
    payload: UpdateCartItemRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
    item = find_owned_cart_item_by_sku_or_id(session, item_id, user_id, session_id)
    update_cart_item_quantity(session, item, payload.quantity)
    return build_cart_payload(get_cart_items(session, user_id, session_id))


@router.delete("/api/v1/cart/items/{item_id}")
def delete_cart_item(
    item_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, session_id = require_cart_identity(authorization, x_session_id)
    item = find_owned_cart_item_by_sku_or_id(session, item_id, user_id, session_id)
    session.delete(item)
    session.commit()
    return build_cart_payload(get_cart_items(session, user_id, session_id))


@router.get("/cart/validate")
@router.get("/api/v1/cart/validate")
@router.post("/api/v1/cart/validate")
def validate_cart(
    cart_item_ids: list[str] | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> dict:
    user_id, _ = require_cart_identity(authorization, None)
    items = get_cart_items(session, user_id, None)
    return build_validation_response(items, cart_item_ids)


@router.post("/api/v1/cart/merge")
def merge_cart(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = user_id_from_authorization(authorization)
    if not user_id:
        raise APIError(401, "UNAUTHORIZED", "Требуется авторизация")
    if not x_session_id:
        raise APIError(400, "MISSING_SESSION_ID", "X-Session-Id is required")
    merge_guest_cart_into_user(session, user_id, x_session_id)
    return build_cart_payload(get_cart_items(session, user_id, None))


@router.get("/api/v1/cart/also_bought")
def get_also_bought(
    limit: int = Query(default=10, ge=1, le=50),
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = user_id_from_authorization(authorization)
    if not user_id:
        raise APIError(401, "UNAUTHORIZED", "Требуется авторизация")
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
