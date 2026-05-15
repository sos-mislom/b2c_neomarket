from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..services import (
    build_facets_response,
    build_similar_products,
    demo_metadata,
    fetch_b2b_catalog,
    fetch_b2b_product_card,
    get_cart_product_ids,
    get_category_or_404,
    get_category_products,
    get_product_by_slug_or_id,
    load_all_products,
    parse_filters,
    product_is_visible,
    product_matches_filters,
    search_products,
    serialize_product_for_catalog,
    serialize_product_for_cart,
    serialize_product_short,
    sort_products,
)


router = APIRouter(tags=["catalog"])


@router.get("/api/v1/products")
def list_products(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    search: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    b2b_catalog = fetch_b2b_catalog(request.query_params)
    if b2b_catalog is not None:
        return b2b_catalog

    filters = parse_filters(request.query_params)
    products = get_category_products(session, category_id)
    products = search_products(products, search)
    products = [product for product in products if product_matches_filters(product, filters)]
    products = sort_products(products, sort)
    cart_product_ids = get_cart_product_ids(session, x_user_id, x_session_id)
    sliced = products[offset : offset + limit]
    return {
        "total_count": len(products),
        "limit": limit,
        "offset": offset,
        "items": [serialize_product_short(product, product.id in cart_product_ids) for product in sliced],
        "meta": demo_metadata(),
    }


@router.get("/api/v1/catalog/facets")
def get_facets(
    request: Request,
    category_id: str = Query(...),
    session: Session = Depends(get_session),
) -> dict:
    get_category_or_404(session, category_id)
    products = get_category_products(session, category_id)
    filters = parse_filters(request.query_params)
    return build_facets_response(products, filters, category_id)


@router.get("/api/v1/products/{id}")
def get_product(
    id: str,
    session: Session = Depends(get_session),
) -> dict:
    b2b_product = fetch_b2b_product_card(id)
    if b2b_product is not None:
        return b2b_product

    product = get_product_by_slug_or_id(session, id)
    if not product_is_visible(product):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found")
    return serialize_product_for_catalog(product)


@router.get("/api/v1/products/{id}/similar")
def get_similar_products(
    id: str,
    limit: int = Query(default=8, ge=1, le=50),
    session: Session = Depends(get_session),
) -> dict:
    product = get_product_by_slug_or_id(session, id)
    if not product_is_visible(product):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found")
    similar = build_similar_products(product, load_all_products(session), limit)
    return {"items": [serialize_product_for_cart(item) for item in similar], "total": len(similar)}
