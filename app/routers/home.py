from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import Banner, BannerEvent, BannerEventType
from ..schemas import BannerEventsRequest
from ..services import demo_metadata, make_id, now_utc


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
