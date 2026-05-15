from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import FavoriteItem
from ..services import (
    assert_product_exists,
    demo_metadata,
    get_product_or_404,
    make_id,
    now_utc,
    product_is_visible,
    require_user_id,
    serialize_product_for_cart,
)


router = APIRouter(tags=["favorites"])


@router.get("/api/v1/favorites")
def list_favorites(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> dict:
    current_user_id = require_user_id(user_id, x_user_id)
    stmt = select(FavoriteItem).where(FavoriteItem.user_id == current_user_id).order_by(FavoriteItem.added_at.desc())
    favorites = list(session.scalars(stmt).all())
    visible_favorites = []
    for favorite in favorites:
        product = get_product_or_404(session, favorite.product_id)
        if product_is_visible(product):
            visible_favorites.append((favorite, product))
    return {
        "items": [
            {"product": serialize_product_for_cart(product), "added_at": favorite.added_at.isoformat()}
            for favorite, product in visible_favorites[offset : offset + limit]
        ],
        "total": len(visible_favorites),
        "meta": demo_metadata(),
    }


@router.post("/api/v1/favorites/{product_id}")
def add_favorite(
    product_id: str,
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> JSONResponse:
    current_user_id = require_user_id(user_id, x_user_id)
    assert_product_exists(session, product_id)
    existing = session.scalar(
        select(FavoriteItem).where(FavoriteItem.user_id == current_user_id, FavoriteItem.product_id == product_id)
    )
    if existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"product_id": product_id, "user_id": current_user_id, "added_at": existing.added_at.isoformat()},
        )
    favorite = FavoriteItem(id=make_id(), user_id=current_user_id, product_id=product_id, added_at=now_utc())
    session.add(favorite)
    session.commit()
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"product_id": product_id, "user_id": current_user_id, "added_at": favorite.added_at.isoformat()},
    )


@router.delete("/api/v1/favorites/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite(
    product_id: str,
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    session: Session = Depends(get_session),
) -> Response:
    current_user_id = require_user_id(user_id, x_user_id)
    assert_product_exists(session, product_id)
    session.execute(delete(FavoriteItem).where(FavoriteItem.user_id == current_user_id, FavoriteItem.product_id == product_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
