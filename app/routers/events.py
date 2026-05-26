from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import Sku
from ..schemas import ProductEventRequest
from ..services import process_product_event, require_service_key


router = APIRouter(tags=["events"])


def normalize_product_event(session: Session, payload: ProductEventRequest) -> tuple[str, list[str], str]:
    event_type = payload.type or payload.event_type
    if event_type is None:
        raise APIError(400, "UNKNOWN_EVENT_TYPE", "event_type is required")

    sku_ids = list(payload.sku_ids)
    event_payload = payload.payload or {}
    raw_sku_ids = event_payload.get("sku_ids")
    if isinstance(raw_sku_ids, list):
        sku_ids.extend(str(sku_id) for sku_id in raw_sku_ids)
    raw_sku_id = event_payload.get("sku_id")
    if raw_sku_id:
        sku_ids.append(str(raw_sku_id))

    product_id = event_payload.get("product_id")
    if product_id and not sku_ids:
        sku_ids.extend(session.scalars(select(Sku.id).where(Sku.product_id == str(product_id))).all())

    return event_type, list(dict.fromkeys(sku_ids)), payload.idempotency_key


@router.post("/api/v1/events/product")
def receive_product_event(
    payload: ProductEventRequest,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    session: Session = Depends(get_session),
) -> dict:
    require_service_key(x_service_key)
    event_type, sku_ids, idempotency_key = normalize_product_event(session, payload)
    return process_product_event(session, event_type, sku_ids, idempotency_key)


@router.post("/api/v1/b2b/events", status_code=status.HTTP_202_ACCEPTED)
def receive_b2b_event(
    payload: ProductEventRequest,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    session: Session = Depends(get_session),
) -> dict:
    require_service_key(x_service_key)
    event_type, sku_ids, idempotency_key = normalize_product_event(session, payload)
    return process_product_event(session, event_type, sku_ids, idempotency_key)
