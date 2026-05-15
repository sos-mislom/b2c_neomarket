from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import Order, OrderStatus
from ..schemas import CancelOrderRequest, CheckoutRequest
from ..services import (
    build_order_list_response,
    cancel_order,
    checkout_cart,
    mark_order_delivered,
    require_service_key,
    require_user_id,
    serialize_order,
)


router = APIRouter(tags=["orders"])


@router.post("/api/v1/orders", status_code=status.HTTP_201_CREATED)
@router.post("/api/v1/orders/checkout", status_code=status.HTTP_201_CREATED)
def create_order_from_cart(
    payload: CheckoutRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    order = checkout_cart(session, user_id, payload.idempotency_key)
    return serialize_order(order)


@router.get("/api/v1/orders")
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    stmt = select(Order).options(selectinload(Order.items)).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)
    orders = list(session.scalars(stmt).all())
    return build_order_list_response(orders, limit, offset)


@router.get("/api/v1/orders/{order_id}")
def get_order(
    order_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.user_id == user_id)
    order = session.scalar(stmt)
    if order is None:
        raise APIError(404, "ORDER_NOT_FOUND", "Order not found")
    return serialize_order(order)


@router.post("/api/v1/orders/{order_id}/cancel")
def cancel_existing_order(
    order_id: str,
    payload: CancelOrderRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    user_id = require_user_id(None, x_user_id)
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.user_id == user_id)
    order = session.scalar(stmt)
    if order is None:
        raise APIError(404, "ORDER_NOT_FOUND", "Order not found")
    cancelled = cancel_order(session, order, payload.reason)
    return serialize_order(cancelled)


@router.post("/api/v1/orders/{order_id}/deliver")
def mark_existing_order_delivered(
    order_id: str,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    session: Session = Depends(get_session),
) -> dict:
    require_service_key(x_service_key)
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    order = session.scalar(stmt)
    if order is None:
        raise APIError(404, "ORDER_NOT_FOUND", "Order not found")
    delivered, fulfill_sent = mark_order_delivered(session, order)
    payload = serialize_order(delivered)
    payload["fulfill_sent"] = fulfill_sent
    return payload
