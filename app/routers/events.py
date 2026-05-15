from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import ProductEventRequest
from ..services import process_product_event, require_service_key


router = APIRouter(tags=["events"])


@router.post("/api/v1/events/product")
def receive_product_event(
    payload: ProductEventRequest,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    session: Session = Depends(get_session),
) -> dict:
    require_service_key(x_service_key)
    return process_product_event(session, payload.type, payload.sku_ids, payload.idempotency_key)
