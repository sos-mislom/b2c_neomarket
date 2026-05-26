from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..services import (
    build_breadcrumbs,
    build_category_maps,
    build_facets_response,
    fetch_b2b_catalog,
    fetch_b2b_product_card,
    fetch_b2b_similar_products,
    build_filters_response,
    build_similar_products,
    category_ref,
    category_slug_path,
    category_subtree_ids,
    demo_metadata,
    get_all_categories,
    get_category_by_slug_path_or_404,
    get_cart_product_ids,
    get_category_or_404,
    get_category_products,
    get_product_by_slug_or_id,
    get_sku_or_404,
    load_all_products,
    parse_filters,
    product_is_visible,
    product_matches_filters,
    search_products,
    serialize_category_node,
    serialize_product_for_catalog,
    serialize_product_short,
    serialize_sku_for_catalog,
    serialize_sku_short_for_catalog,
    sort_products,
)


router = APIRouter(tags=["catalog"])


@router.get("/api/v1/catalog/products")
def list_products(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    q: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> dict:
    b2b_catalog = fetch_b2b_catalog(request.query_params)
    if b2b_catalog is not None:
        return b2b_catalog

    filters = parse_filters(request.query_params)
    products = get_category_products(session, category_id)
    products = search_products(products, q)
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


@router.get("/api/v1/catalog/products/{product_id}")
def get_product(
    product_id: str,
    session: Session = Depends(get_session),
) -> dict:
    b2b_product = fetch_b2b_product_card(product_id)
    if b2b_product is not None:
        return b2b_product

    product = get_product_by_slug_or_id(session, product_id)
    if not product_is_visible(product):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    return serialize_product_for_catalog(product)


@router.get("/api/v1/products/{product_id}/skus")
def get_product_skus(product_id: str, session: Session = Depends(get_session)) -> list[dict]:
    product = get_product_by_slug_or_id(session, product_id)
    if not product_is_visible(product):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    return [serialize_sku_short_for_catalog(sku) for sku in sorted(product.skus, key=lambda item: item.name)]


@router.get("/api/v1/products/{product_id}/skus/{sku_id}")
def get_product_sku(product_id: str, sku_id: str, session: Session = Depends(get_session)) -> dict:
    product = get_product_by_slug_or_id(session, product_id)
    if not product_is_visible(product):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    sku = get_sku_or_404(session, sku_id)
    if sku.product_id != product.id:
        raise APIError(404, "SKU_NOT_FOUND", "SKU с указанным id не существует")
    return serialize_sku_for_catalog(sku)


@router.get("/api/v1/catalog/products/{product_id}/similar")
def get_similar_products(
    request: Request,
    product_id: str,
    category: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session: Session = Depends(get_session),
) -> list[dict]:
    b2b_similar = fetch_b2b_similar_products(product_id, request.query_params)
    if b2b_similar is not None:
        return b2b_similar

    product = get_product_by_slug_or_id(session, product_id)
    all_products = load_all_products(session)
    cart_product_ids = get_cart_product_ids(session, x_user_id, x_session_id)
    if category:
        try:
            get_category_or_404(session, category)
        except APIError as exc:
            if exc.status_code == 404:
                raise APIError(400, "INVALID_REQUEST", "Nonexistent category id") from exc
            raise
        similar = [item for item in build_similar_products(product, all_products, limit + offset + 20) if item.category_id == category]
        sliced = similar[offset : offset + limit]
        return [serialize_product_short(item, item.id in cart_product_ids) for item in sliced]
    similar = build_similar_products(product, all_products, limit + offset)
    sliced = similar[offset : offset + limit]
    return [serialize_product_short(item, item.id in cart_product_ids) for item in sliced]


@router.get("/api/v1/catalog/categories")
@router.get("/api/v1/categories")
def get_categories(session: Session = Depends(get_session)) -> list[dict]:
    categories = get_all_categories(session, active_only=True)
    by_id, _ = build_category_maps(categories)
    return [category_ref(category, by_id) for category in categories]


@router.get("/api/v1/catalog/categories/tree")
@router.get("/api/v1/categories/tree")
def get_category_tree(session: Session = Depends(get_session)) -> list[dict]:
    categories = get_all_categories(session, active_only=True)
    by_id, children_map = build_category_maps(categories)
    roots = children_map.get(None, [])
    return [serialize_category_node(category, children_map, by_id) for category in roots]


@router.get("/api/v1/catalog/categories/path/{slug_path:path}")
@router.get("/api/v1/categories/path/{slug_path:path}")
def get_category_by_path(
    slug_path: str,
    include_product_count: bool = Query(default=False),
    lang: str = Query(default="ru"),
    session: Session = Depends(get_session),
) -> dict:
    category = get_category_by_slug_path_or_404(session, slug_path)
    return get_category_detail(category.id, include_product_count=include_product_count, lang=lang, session=session)


@router.get("/api/v1/catalog/categories/{id}")
@router.get("/api/v1/categories/{id}")
def get_category_detail(
    id: str,
    include_product_count: bool = Query(default=False),
    lang: str = Query(default="ru"),
    session: Session = Depends(get_session),
) -> dict:
    if lang not in {"ru", "en"}:
        raise APIError(400, "INVALID_LANG", "Поддерживаются только языки ru и en")
    category = get_category_or_404(session, id)
    if not category.is_active:
        raise APIError(404, "CATEGORY_NOT_FOUND", "РљР°С‚РµРіРѕСЂРёСЏ РЅРµ РЅР°Р№РґРµРЅР°")
    categories = get_all_categories(session, active_only=True)
    by_id, children_map = build_category_maps(categories)
    parent = by_id.get(category.parent_id) if category.parent_id else None
    product_count = None
    if include_product_count:
        subtree_ids = category_subtree_ids(children_map, category.id)
        product_count = len(
            [product for product in load_all_products(session) if product.category_id in subtree_ids and product_is_visible(product)]
        )
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "parent": None if parent is None else {"id": parent.id, "name": parent.name, "slug": parent.slug},
        "product_count": product_count,
        "seo": {
            "title": category.seo_title,
            "description": category.seo_description,
            "keywords": category.seo_keywords,
        },
        "meta_tags": category.meta_tags,
        "image_url": category.image_url,
        "is_active": category.is_active,
        "created_at": category.created_at.isoformat(),
        "updated_at": category.updated_at.isoformat(),
    }


@router.get("/api/v1/catalog/categories/{id}/filters")
@router.get("/api/v1/categories/{id}/filters")
def get_category_filters(id: str, session: Session = Depends(get_session)) -> dict:
    get_category_or_404(session, id)
    products = get_category_products(session, id)
    return build_filters_response(products)


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


@router.get("/api/v1/catalog/breadcrumbs")
@router.get("/api/v1/breadcrumbs")
def get_breadcrumbs(
    category_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    lang: str = Query(default="ru"),
    session: Session = Depends(get_session),
) -> dict:
    if lang not in {"ru", "en", "kk"}:
        raise APIError(400, "invalid_param", "parameter must be a valid language code")
    if bool(category_id) == bool(product_id):
        raise APIError(
            400,
            "ambiguous_param" if category_id and product_id else "missing_param",
            "only one of category_id or product_id must be provided" if category_id and product_id else "category_id or product_id must be provided",
        )

    categories = get_all_categories(session, active_only=True)
    by_id, _ = build_category_maps(categories)
    resolved_category_id = category_id
    resolved_via = "category_id"
    if product_id:
        product = get_product_by_slug_or_id(session, product_id)
        resolved_category_id = product.category_id
        resolved_via = "product_id"
    if resolved_category_id not in by_id:
        raise APIError(404, "category_not_found", "category not found")
    chain = build_breadcrumbs(by_id, resolved_category_id)
    return {
        "data": [
            {
                "id": category.id,
                "slug": category.slug,
                "name": category.name,
                "url": category_slug_path(chain[: index + 1]),
                "level": index,
                "is_current": index == len(chain) - 1,
            }
            for index, category in enumerate(chain)
        ],
        "meta": {"resolved_via": resolved_via, "category_id": resolved_category_id, "product_id": product_id},
    }
