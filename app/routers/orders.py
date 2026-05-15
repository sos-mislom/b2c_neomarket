from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import CheckoutRequest
from ..services import checkout_cart, require_user_id, serialize_order


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
