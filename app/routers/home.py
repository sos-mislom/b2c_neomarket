from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import Banner, BannerEvent, BannerEventType, Collection, CollectionProduct
from ..schemas import BannerEventsRequest
from ..services import (
    demo_metadata,
    get_collection_by_slug_or_id,
    get_product_or_404,
    make_id,
    now_utc,
    product_is_visible,
    serialize_collection,
    serialize_product_for_cart,
)


router = APIRouter(tags=["home"])


def as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/api/v1/home/banners")
def get_home_banners(session: Session = Depends(get_session)) -> dict:
    now = now_utc().replace(tzinfo=None)
    stmt = select(Banner).where(Banner.is_active.is_(True), Banner.placement == "home").order_by(Banner.priority.asc())
    banners = []
    for banner in session.scalars(stmt).all():
        start_at = as_utc_naive(banner.start_at)
        end_at = as_utc_naive(banner.end_at) if banner.end_at else None
        if start_at <= now and (end_at is None or end_at >= now):
            banners.append(banner)
    return {
        "items": [
            {
                "id": banner.id,
                "title": banner.title,
                "image_url": banner.image_url,
                "link": banner.link,
                "priority": banner.priority,
            }
            for banner in banners
        ],
        "total_count": len(banners),
        "meta": demo_metadata(),
    }


@router.post("/api/v1/banner-events", status_code=status.HTTP_204_NO_CONTENT)
def post_banner_events(
    payload: BannerEventsRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> Response:
    for event in payload.events:
        banner = session.get(Banner, event.banner_id)
        if banner is None:
            raise APIError(400, "BANNER_NOT_FOUND", "Banner not found")
        session.add(
            BannerEvent(
                id=make_id(),
                banner_id=event.banner_id,
                user_id=x_user_id,
                session_id=x_session_id,
                event=BannerEventType(event.event),
                client_timestamp=event.timestamp,
                created_at=now_utc(),
            )
        )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/v1/main/collections")
def list_collections(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    today = date.today()
    stmt = select(Collection).where(Collection.is_active.is_(True), Collection.start_date <= today).order_by(Collection.priority.asc())
    collections = list(session.scalars(stmt).all())
    sliced = collections[offset : offset + limit]
    return {
        "metadata": {"total_count": len(collections), "limit": limit, "offset": offset},
        "collections": [serialize_collection(collection, product_count=len(collection.products)) for collection in sliced],
    }


@router.get("/api/v1/collections/{collection_ref}/products")
def get_collection_products(
    collection_ref: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    collection = get_collection_by_slug_or_id(session, collection_ref)
    links = list(
        session.scalars(
            select(CollectionProduct).where(CollectionProduct.collection_id == collection.id).order_by(CollectionProduct.ordering.asc())
        ).all()
    )
    unavailable_ids = []
    items = []
    for link in links:
        product = get_product_or_404(session, link.product_id)
        if product_is_visible(product):
            items.append(serialize_product_for_cart(product))
        else:
            unavailable_ids.append(product.id)
    return {
        "collection": serialize_collection(collection, product_count=len(items)),
        "total_products": len(items),
        "items": items[offset : offset + limit],
        "unavailable_ids": unavailable_ids,
    }
