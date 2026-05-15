from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from .config import get_settings
from .errors import APIError
from .models import (
    Banner,
    BannerEvent,
    BannerEventType,
    CartItem,
    Category,
    Collection,
    CollectionProduct,
    FavoriteItem,
    NotificationSubscription,
    Order,
    OrderItem,
    OrderStatus,
    ProcessedEvent,
    Product,
    ProductStatus,
    Sku,
    Store,
)


PRODUCT_LOADERS = (
    joinedload(Product.store),
    joinedload(Product.category),
    selectinload(Product.images),
    selectinload(Product.characteristics),
    selectinload(Product.skus).selectinload(Sku.images),
    selectinload(Product.skus).selectinload(Sku.characteristics),
)

DISPLAY_NAMES = {
    "store": "Магазин",
    "brand": "Бренд",
    "origin": "Происхождение",
    "tea_type": "Тип чая",
    "taste": "Вкус",
    "caffeine": "Кофеин",
    "leaf": "Формат",
    "harvest": "Сбор",
    "format": "Формат набора",
    "original": "Оригинальный товар",
}
FILTER_PRIORITY = {
    "store": 0,
    "brand": 1,
    "tea_type": 2,
    "origin": 3,
    "taste": 4,
    "caffeine": 5,
    "leaf": 6,
    "harvest": 7,
    "format": 8,
    "original": 9,
}
RESERVED_QUERY_KEYS = {
    "limit",
    "offset",
    "sort",
    "search",
    "category_id",
    "filters",
    "include_product_count",
    "lang",
    "category",
    "product_id",
}
CHECKOUT_CANCELABLE = {OrderStatus.CREATED, OrderStatus.PAID}


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def cents_to_rub(cents: int) -> float:
    return round(cents / 100, 2)


def make_id() -> str:
    return str(uuid4())


def slugify_characteristic(name: str) -> str:
    return name.lower().replace(" ", "_")


def require_cart_identity(x_user_id: str | None, x_session_id: str | None) -> tuple[str | None, str | None]:
    if not x_user_id and not x_session_id:
        raise APIError(400, "MISSING_CART_IDENTITY", "Передайте X-User-Id или X-Session-Id")
    return x_user_id, x_session_id


def require_user_id(query_user_id: str | None, x_user_id: str | None) -> str:
    user_id = x_user_id or query_user_id
    if not user_id:
        raise APIError(401, "UNAUTHORIZED", "Требуется авторизация")
    return user_id


def load_all_products(session: Session) -> list[Product]:
    stmt = select(Product).options(*PRODUCT_LOADERS).order_by(Product.created_at.desc())
    return list(session.scalars(stmt).unique().all())


def get_product_or_404(session: Session, product_id: str) -> Product:
    stmt = select(Product).options(*PRODUCT_LOADERS).where(Product.id == product_id)
    product = session.scalar(stmt)
    if product is None:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    return product


def get_product_by_slug_or_id(session: Session, product_id: str) -> Product:
    stmt = select(Product).options(*PRODUCT_LOADERS).where(or_(Product.id == product_id, Product.slug == product_id))
    product = session.scalar(stmt)
    if product is None:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    return product


def get_sku_or_404(session: Session, sku_id: str) -> Sku:
    stmt = (
        select(Sku)
        .options(
            joinedload(Sku.product).joinedload(Product.store),
            joinedload(Sku.product).joinedload(Product.category),
            selectinload(Sku.images),
            selectinload(Sku.characteristics),
        )
        .where(Sku.id == sku_id)
    )
    sku = session.scalar(stmt)
    if sku is None:
        raise APIError(404, "SKU_NOT_FOUND", "SKU с указанным id не существует")
    return sku


def get_category_or_404(session: Session, category_id: str) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Категория не найдена")
    return category


def get_collection_or_404(session: Session, collection_id: str) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise APIError(404, "COLLECTION_NOT_FOUND", "Подборка не найдена")
    return collection


def collection_slug(collection: Collection) -> str:
    return collection.target_url.rstrip("/").split("/")[-1]


def get_collection_by_slug_or_id(session: Session, collection_ref: str) -> Collection:
    stmt = select(Collection).where(or_(Collection.id == collection_ref, Collection.target_url == f"/collections/{collection_ref}"))
    collection = session.scalar(stmt)
    if collection is None:
        raise APIError(404, "COLLECTION_NOT_FOUND", "Подборка не найдена")
    return collection


def get_category_by_slug_path_or_404(session: Session, slug_path: str) -> Category:
    slugs = [segment.strip() for segment in slug_path.split("/") if segment.strip()]
    if not slugs:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Категория не найдена")

    categories = get_all_categories(session)
    _, children_map = build_category_maps(categories)
    current_parent_id = None
    current_category = None

    for slug in slugs:
        current_category = next((item for item in children_map.get(current_parent_id, []) if item.slug == slug), None)
        if current_category is None:
            raise APIError(404, "CATEGORY_NOT_FOUND", "Категория не найдена")
        current_parent_id = current_category.id

    return current_category


def product_available_skus(product: Product) -> list[Sku]:
    return [sku for sku in product.skus if sku.is_active and sku.active_quantity > 0]


def product_is_visible(product: Product) -> bool:
    return (
        product.status == ProductStatus.MODERATED
        and not product.is_deleted
        and not product.is_blocked
        and any(sku.is_active and sku.active_quantity > 0 for sku in product.skus)
    )


def product_main_image(product: Product) -> str | None:
    if not product.images:
        return None
    return min(product.images, key=lambda item: item.ordering).url


def sku_main_image(sku: Sku) -> str | None:
    if sku.images:
        return min(sku.images, key=lambda item: item.ordering).url
    if sku.product:
        return product_main_image(sku.product)
    return None


def product_min_price(product: Product, only_available: bool = True) -> int:
    skus = product_available_skus(product) if only_available else [sku for sku in product.skus if sku.is_active]
    if not skus:
        return min((sku.price_cents for sku in product.skus), default=0)
    return min(sku.price_cents for sku in skus)


def product_default_sku(product: Product) -> Sku | None:
    preferred = sorted(product_available_skus(product), key=lambda item: (item.price_cents, item.name))
    if preferred:
        return preferred[0]
    fallback = sorted([sku for sku in product.skus if sku.is_active], key=lambda item: (item.price_cents, item.name))
    return fallback[0] if fallback else None


def product_brand(product: Product) -> str | None:
    for characteristic in product.characteristics:
        if slugify_characteristic(characteristic.name) == "brand":
            return str(characteristic.value)
    return None


def serialize_store(store: Store | None) -> dict | None:
    if store is None:
        return None
    return {
        "id": store.id,
        "slug": store.slug,
        "name": store.name,
        "rating": store.rating,
        "delivery_note": store.delivery_note,
        "logo_url": store.logo_url,
    }


def serialize_images(items, order_field: str = "ordering") -> list[dict]:
    ordered = sorted(items, key=lambda item: getattr(item, order_field))
    return [{"url": item.url, "order": getattr(item, order_field)} for item in ordered]


def serialize_characteristics(items) -> list[dict]:
    return [{"name": item.name, "value": item.value} for item in items]


def normalize_b2c_images(images: list[dict | str] | None) -> list[dict]:
    normalized = []
    for index, image in enumerate(images or []):
        if isinstance(image, str):
            normalized.append({"url": image, "ordering": index})
            continue
        item = dict(image)
        if "ordering" not in item and "order" in item:
            item["ordering"] = item.pop("order")
        normalized.append(item)
    return normalized


def b2b_headers() -> dict[str, str]:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.b2b_service_key:
        headers["X-Service-Key"] = settings.b2b_service_key
    if settings.b2b_auth_token:
        headers["Authorization"] = f"Bearer {settings.b2b_auth_token}"
    return headers


def sanitize_b2b_product_card(payload: dict) -> dict:
    product = dict(payload)
    product["images"] = normalize_b2c_images(product.get("images"))

    skus = []
    for sku_payload in product.get("skus") or []:
        sku = {key: value for key, value in dict(sku_payload).items() if key not in {"cost_price", "reserved_quantity"}}
        if "active_quantity" not in sku and "quantity" in sku:
            sku["active_quantity"] = sku["quantity"]
        if "in_stock" not in sku:
            sku["in_stock"] = bool(sku.get("active_quantity", 0) > 0)
        skus.append(sku)
    product["skus"] = skus
    return product


def fetch_b2b_catalog(query_params) -> dict | None:
    settings = get_settings()
    if not settings.b2b_base_url:
        return None

    try:
        response = httpx.get(
            f"{settings.b2b_base_url.rstrip('/')}/api/v1/products",
            params=list(query_params.multi_items()),
            headers=b2b_headers(),
            timeout=settings.b2b_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise APIError(503, "B2B_UNAVAILABLE", "B2B product service is unavailable") from exc

    if response.status_code >= 500:
        raise APIError(503, "B2B_UNAVAILABLE", "B2B product service is unavailable")
    if response.status_code >= 400:
        raise APIError(response.status_code, "B2B_ERROR", "B2B product service rejected request")

    payload = response.json()
    items = payload.get("items", payload if isinstance(payload, list) else [])
    if isinstance(items, list):
        sanitized_items = [sanitize_b2b_product_card(item) for item in items]
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["items"] = sanitized_items
        else:
            payload = {"items": sanitized_items, "total_count": len(sanitized_items)}
    return payload


def fetch_b2b_product_card(product_id: str) -> dict | None:
    settings = get_settings()
    if not settings.b2b_base_url:
        return None

    try:
        response = httpx.get(
            f"{settings.b2b_base_url.rstrip('/')}/api/v1/products/{product_id}",
            headers=b2b_headers(),
            timeout=settings.b2b_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise APIError(503, "B2B_UNAVAILABLE", "B2B product service is unavailable") from exc

    if response.status_code == 404:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    if response.status_code >= 500:
        raise APIError(503, "B2B_UNAVAILABLE", "B2B product service is unavailable")
    if response.status_code >= 400:
        raise APIError(response.status_code, "B2B_ERROR", "B2B product service rejected request")

    payload = response.json()
    if payload.get("status") in {"BLOCKED", "HARD_BLOCKED"} or payload.get("deleted") is True or payload.get("is_deleted") is True:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    return sanitize_b2b_product_card(payload)


def serialize_product_for_catalog(product: Product) -> dict:
    default_sku = product_default_sku(product)
    return {
        "id": product.id,
        "slug": product.slug,
        "title": product.title,
        "description": product.description,
        "images": [{"url": image["url"], "ordering": image["order"]} for image in serialize_images(product.images)],
        "status": product.status.value,
        "store": serialize_store(product.store),
        "brand": product_brand(product),
        "rating": product.rating,
        "popularity": product.popularity,
        "discount_percent": product.discount_percent,
        "price_from": cents_to_rub(product_min_price(product)),
        "default_sku_id": default_sku.id if default_sku else None,
        "category": {"id": product.category.id, "name": product.category.name},
        "characteristics": serialize_characteristics(product.characteristics),
        "skus": [serialize_sku_for_catalog(sku) for sku in sorted(product.skus, key=lambda item: (item.price_cents, item.name))],
    }


def serialize_product_for_cart(product: Product) -> dict:
    default_sku = product_default_sku(product)
    return {
        "id": product.id,
        "slug": product.slug,
        "title": product.title,
        "description": product.description,
        "status": product.status.value,
        "store": serialize_store(product.store),
        "brand": product_brand(product),
        "rating": product.rating,
        "popularity": product.popularity,
        "discount_percent": product.discount_percent,
        "price_from": cents_to_rub(product_min_price(product)),
        "default_sku_id": default_sku.id if default_sku else None,
        "category": {"id": product.category.id, "name": product.category.name},
        "images": [{"url": image["url"], "ordering": image["order"]} for image in serialize_images(product.images)],
        "characteristics": serialize_characteristics(product.characteristics),
        "skus": [serialize_sku_for_cart(sku) for sku in sorted(product.skus, key=lambda item: (item.price_cents, item.name))],
    }


def serialize_product_short(product: Product, is_in_cart: bool) -> dict:
    default_sku = product_default_sku(product)
    return {
        "id": product.id,
        "slug": product.slug,
        "title": product.title,
        "image": product_main_image(product),
        "store": serialize_store(product.store),
        "brand": product_brand(product),
        "rating": product.rating,
        "popularity": product.popularity,
        "discount_percent": product.discount_percent,
        "default_sku_id": default_sku.id if default_sku else None,
        "price": cents_to_rub(product_min_price(product)),
        "in_stock": any(sku.active_quantity > 0 and sku.is_active for sku in product.skus),
        "is_in_cart": is_in_cart,
    }


def serialize_collection(collection: Collection, product_count: int | None = None) -> dict:
    payload = {
        "id": collection.id,
        "slug": collection_slug(collection),
        "title": collection.title,
        "description": collection.description,
        "cover_image_url": collection.cover_image_url,
        "target_url": collection.target_url,
        "priority": collection.priority,
        "start_date": collection.start_date.isoformat(),
    }
    if product_count is not None:
        payload["product_count"] = product_count
    return payload


def serialize_sku_for_catalog(sku: Sku) -> dict:
    discount = 0
    if sku.product and sku.product.discount_percent > 0:
        discount = round(sku.price_cents * sku.product.discount_percent / 100)
    return {
        "id": sku.id,
        "name": sku.name,
        "price": sku.price_cents,
        "discount": discount,
        "image": sku_main_image(sku),
        "active_quantity": sku.active_quantity,
        "in_stock": sku.is_active and sku.active_quantity > 0,
        "characteristics": serialize_characteristics(sku.characteristics),
        "images": serialize_images(sku.images),
    }


def serialize_sku_short_for_catalog(sku: Sku) -> dict:
    main_image = sku_main_image(sku)
    return {
        "name": sku.name,
        "price": cents_to_rub(sku.price_cents),
        "image": {"url": main_image, "order": 0},
    }


def serialize_sku_for_cart(sku: Sku) -> dict:
    return {
        "id": sku.id,
        "name": sku.name,
        "price": sku.price_cents,
        "active_quantity": sku.active_quantity,
        "characteristics": serialize_characteristics(sku.characteristics),
    }


def get_all_categories(session: Session) -> list[Category]:
    stmt = select(Category).order_by(Category.name.asc())
    return list(session.scalars(stmt).all())


def build_category_maps(categories: list[Category]) -> tuple[dict[str, Category], dict[str | None, list[Category]]]:
    by_id = {category.id: category for category in categories}
    children: dict[str | None, list[Category]] = defaultdict(list)
    for category in categories:
        children[category.parent_id].append(category)
    for category_list in children.values():
        category_list.sort(key=lambda item: item.name)
    return by_id, children


def serialize_category_node(category: Category, children_map: dict[str | None, list[Category]]) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
        "children": [serialize_category_node(child, children_map) for child in children_map.get(category.id, [])],
    }


def category_subtree_ids(children_map: dict[str | None, list[Category]], category_id: str) -> set[str]:
    result = {category_id}
    for child in children_map.get(category_id, []):
        result.update(category_subtree_ids(children_map, child.id))
    return result


def build_breadcrumbs(by_id: dict[str, Category], category_id: str) -> list[Category]:
    chain = []
    current = by_id.get(category_id)
    seen = set()
    while current is not None:
        if current.id in seen:
            raise APIError(422, "orphan_node", "category hierarchy is broken")
        seen.add(current.id)
        chain.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None
    chain.reverse()
    return chain


def category_slug_path(chain: list[Category]) -> str:
    return "/catalog/" + "/".join(category.slug for category in chain)


def get_cart_items(session: Session, user_id: str | None, session_id: str | None) -> list[CartItem]:
    stmt = (
        select(CartItem)
        .options(
            joinedload(CartItem.sku).joinedload(Sku.product).joinedload(Product.store),
            joinedload(CartItem.sku).joinedload(Sku.product).joinedload(Product.category),
            joinedload(CartItem.sku).selectinload(Sku.images),
            joinedload(CartItem.sku).selectinload(Sku.characteristics),
            joinedload(CartItem.sku).joinedload(Sku.product).selectinload(Product.images),
            joinedload(CartItem.sku).joinedload(Sku.product).selectinload(Product.characteristics),
        )
        .order_by(CartItem.created_at.asc())
    )
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    else:
        stmt = stmt.where(CartItem.session_id == session_id)
    return list(session.scalars(stmt).unique().all())


def merge_guest_cart_into_user(session: Session, user_id: str | None, session_id: str | None) -> None:
    if not user_id or not session_id:
        return

    guest_items = list(session.scalars(select(CartItem).where(CartItem.session_id == session_id)).all())
    if not guest_items:
        return

    for guest_item in guest_items:
        existing = session.scalar(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.sku_id == guest_item.sku_id)
        )
        if existing is None:
            guest_item.user_id = user_id
            guest_item.session_id = None
            guest_item.updated_at = now_utc()
            continue

        existing.quantity = max(existing.quantity, guest_item.quantity)
        existing.updated_at = now_utc()
        session.delete(guest_item)
    session.commit()


def cart_item_unavailable_reason(cart_item: CartItem) -> str | None:
    if cart_item.unavailable_reason:
        return cart_item.unavailable_reason
    sku = cart_item.sku
    product = sku.product if sku else None
    if sku is None or product is None or product.is_deleted:
        return "PRODUCT_DELISTED"
    if product.is_blocked or product.status == ProductStatus.BLOCKED:
        return "PRODUCT_BLOCKED"
    if product.status != ProductStatus.MODERATED:
        return "PRODUCT_DELISTED"
    if not sku.is_active:
        return "SKU_DISABLED"
    if sku.active_quantity <= 0 or sku.active_quantity < cart_item.quantity:
        return "OUT_OF_STOCK"
    return None


def require_service_key(x_service_key: str | None) -> None:
    expected = get_settings().b2b_service_key
    if not expected or x_service_key != expected:
        raise APIError(401, "UNAUTHORIZED", "X-Service-Key is missing or invalid")


def process_product_event(
    session: Session,
    event_type: str,
    sku_ids: list[str],
    idempotency_key: str,
) -> dict:
    normalized_type = event_type.upper()
    reason_by_type = {
        "PRODUCT_BLOCKED": "PRODUCT_BLOCKED",
        "PRODUCT_DELETED": "PRODUCT_DELISTED",
        "SKU_OUT_OF_STOCK": "OUT_OF_STOCK",
        "OUT_OF_STOCK": "OUT_OF_STOCK",
    }
    if normalized_type not in reason_by_type:
        raise APIError(400, "UNKNOWN_EVENT_TYPE", "Unsupported product event type")
    if not sku_ids:
        raise APIError(400, "EMPTY_SKU_IDS", "sku_ids must not be empty")

    existing = session.get(ProcessedEvent, idempotency_key)
    if existing is not None:
        return {"processed": False, "updated": 0}

    items = list(session.scalars(select(CartItem).where(CartItem.sku_id.in_(sku_ids))).all())
    reason = reason_by_type[normalized_type]
    now = now_utc()
    for item in items:
        item.unavailable_reason = reason
        item.updated_at = now

    session.add(ProcessedEvent(idempotency_key=idempotency_key, event_type=normalized_type, created_at=now))
    session.commit()
    return {"processed": True, "updated": len(items)}


def serialize_cart_item(cart_item: CartItem) -> dict:
    sku = cart_item.sku
    product = sku.product
    unavailable_reason = cart_item_unavailable_reason(cart_item)
    available = unavailable_reason is None
    unit_price = sku.price_cents if sku else 0
    return {
        "item_id": cart_item.id,
        "sku_id": sku.id,
        "product_id": product.id,
        "product_title": product.title,
        "store_name": product.store.name if product.store else None,
        "sku_name": sku.name,
        "image_url": sku_main_image(sku),
        "unit_price": unit_price,
        "quantity": cart_item.quantity,
        "available_stock": sku.active_quantity,
        "line_total": unit_price * cart_item.quantity if available else 0,
        "available": available,
        "unavailable_reason": unavailable_reason,
    }


def build_cart_payload(items: list[CartItem]) -> dict:
    serialized_items = [serialize_cart_item(item) for item in items]
    total_amount = sum(item["line_total"] for item in serialized_items if item["available"])
    total_items = len(serialized_items)
    total_quantity = sum(item["quantity"] for item in serialized_items)
    available_items = sum(1 for item in serialized_items if item["available"])
    checkout_items = [
        {
            "product_id": item["product_id"],
            "sku_id": item["sku_id"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "line_total": item["line_total"],
        }
        for item in serialized_items
        if item["available"]
    ]
    return {
        "items": serialized_items,
        "summary": {
            "total_amount": total_amount,
            "total_items": total_items,
            "total_quantity": total_quantity,
            "available_items": available_items,
            "has_unavailable_items": any(not item["available"] for item in serialized_items),
            "checkout_ready": total_items > 0 and all(item["available"] for item in serialized_items),
            "currency": "RUB",
        },
        "checkout_payload": {
            "items": checkout_items,
            "total_amount": total_amount,
            "currency": "RUB",
        },
    }


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status.value,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "can_cancel": order.status in CHECKOUT_CANCELABLE,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "sku_id": item.sku_id,
                "product_title": item.product_title,
                "sku_name": item.sku_name,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
                "line_total": item.line_total,
            }
            for item in order.items
        ],
    }


def char_values_for_product(product: Product, slug: str) -> set[str]:
    values: set[str] = set()
    if slug == "store" and product.store:
        values.add(product.store.name)
    for characteristic in product.characteristics:
        if slugify_characteristic(characteristic.name) == slug:
            values.add(str(characteristic.value))
    for sku in product_available_skus(product):
        for characteristic in sku.characteristics:
            if slugify_characteristic(characteristic.name) == slug:
                values.add(str(characteristic.value))
    return values


def parse_filters(query_params) -> dict[str, object]:
    parsed: dict[str, object] = {}

    def merge_value(key: str, values: list[str]) -> None:
        if not values:
            return
        if key in parsed:
            current = parsed[key]
            current_list = current if isinstance(current, list) else [current]
            parsed[key] = current_list + values
        else:
            parsed[key] = values if len(values) > 1 else values[0]

    for key in query_params.keys():
        values = query_params.getlist(key)
        if key.startswith("filters[") and key.endswith("]"):
            merge_value(key[8:-1], values)
        elif key == "filters":
            for raw_value in values:
                try:
                    payload = json.loads(raw_value)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    for inner_key, inner_value in payload.items():
                        if isinstance(inner_value, list):
                            merge_value(inner_key, [str(item) for item in inner_value])
                        else:
                            merge_value(inner_key, [str(inner_value)])
        elif key not in RESERVED_QUERY_KEYS:
            merge_value(key, values)
    return parsed


def normalize_filter_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def product_matches_filters(product: Product, filters: dict[str, object]) -> bool:
    if not filters:
        return True

    for key, raw_value in filters.items():
        values = normalize_filter_values(raw_value)
        lowered_values = {value.lower() for value in values}
        if key == "price_min":
            if product_min_price(product) < int(values[0]):
                return False
            continue
        if key == "price_max":
            if product_min_price(product) > int(values[0]):
                return False
            continue
        if key == "original":
            product_values = {value.lower() for value in char_values_for_product(product, key)}
            if not product_values.intersection(lowered_values):
                return False
            continue

        product_values = {value.lower() for value in char_values_for_product(product, key)}
        if not product_values.intersection(lowered_values):
            return False
    return True


def search_products(products: list[Product], search: str | None) -> list[Product]:
    if not search:
        return products
    normalized = search.strip().lower()
    if len(normalized) < 3:
        raise APIError(400, "INVALID_SEARCH", "Поисковый запрос должен содержать не менее 3 символов")
    return [
        product
        for product in products
        if normalized in product.title.lower()
        or normalized in product.description.lower()
        or normalized in (product_brand(product) or "").lower()
        or normalized in (product.store.name.lower() if product.store else "")
    ]


def sort_products(products: list[Product], sort: str | None) -> list[Product]:
    if sort is None:
        return sorted(products, key=lambda item: item.popularity, reverse=True)
    if sort == "rating":
        return sorted(products, key=lambda item: item.rating, reverse=True)
    if sort == "popularity":
        return sorted(products, key=lambda item: item.popularity, reverse=True)
    if sort == "price_asc":
        return sorted(products, key=lambda item: product_min_price(item))
    if sort == "price_desc":
        return sorted(products, key=lambda item: product_min_price(item), reverse=True)
    if sort == "date_desc":
        return sorted(products, key=lambda item: item.created_at, reverse=True)
    if sort == "discount_desc":
        return sorted(products, key=lambda item: item.discount_percent, reverse=True)
    raise APIError(
        400,
        "INVALID_SORT",
        "Invalid sort parameter. Allowed values: rating, popularity, price_asc, price_desc, date_desc, discount_desc",
    )


def get_category_products(session: Session, category_id: str | None) -> list[Product]:
    products = load_all_products(session)
    if not category_id:
        return [product for product in products if product_is_visible(product)]
    categories = get_all_categories(session)
    by_id, children = build_category_maps(categories)
    if category_id not in by_id:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Категория не найдена")
    allowed_category_ids = category_subtree_ids(children, category_id)
    return [product for product in products if product.category_id in allowed_category_ids and product_is_visible(product)]


def get_cart_product_ids(session: Session, user_id: str | None, session_id: str | None) -> set[str]:
    if not user_id and not session_id:
        return set()
    cart_items = get_cart_items(session, user_id, session_id)
    return {item.sku.product_id for item in cart_items}


def build_filters_response(products: list[Product]) -> dict:
    buckets: dict[str, set[str]] = defaultdict(set)
    min_price = None
    max_price = None
    for product in products:
        if product.store:
            buckets["store"].add(product.store.name)
        for characteristic in product.characteristics:
            buckets[slugify_characteristic(characteristic.name)].add(str(characteristic.value))
        for sku in product_available_skus(product):
            min_price = sku.price_cents if min_price is None else min(min_price, sku.price_cents)
            max_price = sku.price_cents if max_price is None else max(max_price, sku.price_cents)
            for characteristic in sku.characteristics:
                buckets[slugify_characteristic(characteristic.name)].add(str(characteristic.value))

    items = []
    for slug, values in sorted(buckets.items(), key=lambda item: (FILTER_PRIORITY.get(item[0], 50), item[0])):
        if slug == "original":
            items.append({"slug": slug, "name": DISPLAY_NAMES.get(slug, slug), "type": "switch"})
            continue
        items.append(
            {
                "slug": slug,
                "name": DISPLAY_NAMES.get(slug, slug.replace("_", " ").title()),
                "type": "list",
                "value": sorted(values, key=lambda item: (len(item), item)),
            }
        )

    if min_price is not None and max_price is not None:
        items.append({"slug": "price", "name": "Цена", "type": "range", "min": min_price, "max": max_price})
    return {"items": items}


def build_facets_response(products: list[Product], filters: dict[str, object], category_id: str) -> dict:
    all_slugs: set[str] = set()
    for product in products:
        if product.store:
            all_slugs.add("store")
        for characteristic in product.characteristics:
            all_slugs.add(slugify_characteristic(characteristic.name))
        for sku in product_available_skus(product):
            for characteristic in sku.characteristics:
                all_slugs.add(slugify_characteristic(characteristic.name))

    facets = []
    for slug in sorted(all_slugs, key=lambda item: (FILTER_PRIORITY.get(item, 50), item)):
        filtered_without_current = {
            key: value for key, value in filters.items() if key not in {slug, "price_min", "price_max"}
        }
        base_products = [product for product in products if product_matches_filters(product, filtered_without_current)]
        counter: Counter[str] = Counter()
        for product in base_products:
            values = char_values_for_product(product, slug)
            for value in values:
                counter[value] += 1
        facets.append(
            {
                "name": slug,
                "values": [{"value": value, "count": count} for value, count in sorted(counter.items())],
            }
        )
    return {"category_id": category_id, "facets": facets}


def build_validation_response(items: list[CartItem], cart_item_ids: list[str] | None = None) -> dict:
    if cart_item_ids:
        lookup = {item.id: item for item in items}
        missing = [item_id for item_id in cart_item_ids if item_id not in lookup]
        if missing:
            raise APIError(400, "CART_ITEMS_NOT_FOUND", f"Указанные позиции не найдены: {', '.join(missing)}")
        items = [lookup[item_id] for item_id in cart_item_ids]

    issues = []
    for item in items:
        sku = item.sku
        product = sku.product
        if product.is_deleted or sku is None:
            issues.append(
                {
                    "cart_item_id": item.id,
                    "sku_id": item.sku_id,
                    "issue_type": "DELETED",
                    "severity": "critical",
                    "message": "Товар удалён продавцом",
                    "details": {
                        "product_id": None,
                        "product_title": None,
                        "sku_name": None,
                    },
                }
            )
            continue
        if product.status == ProductStatus.BLOCKED or product.is_blocked:
            issues.append(
                {
                    "cart_item_id": item.id,
                    "sku_id": item.sku_id,
                    "issue_type": "BLOCKED",
                    "severity": "critical",
                    "message": "Товар заблокирован модератором и недоступен для покупки",
                    "details": {
                        "product_id": product.id,
                        "product_title": product.title,
                        "sku_name": sku.name,
                        "current_status": product.status.value,
                    },
                }
            )
            continue
        if product.status in {ProductStatus.CREATED, ProductStatus.ON_MODERATION}:
            issues.append(
                {
                    "cart_item_id": item.id,
                    "sku_id": item.sku_id,
                    "issue_type": "ON_MODERATION",
                    "severity": "warning",
                    "message": "Товар ещё не прошёл модерацию",
                    "details": {
                        "product_id": product.id,
                        "product_title": product.title,
                        "sku_name": sku.name,
                        "current_status": product.status.value,
                    },
                }
            )
        if sku.active_quantity <= 0:
            issues.append(
                {
                    "cart_item_id": item.id,
                    "sku_id": item.sku_id,
                    "issue_type": "OUT_OF_STOCK",
                    "severity": "critical",
                    "message": "Товар отсутствует в наличии",
                    "details": {
                        "product_id": product.id,
                        "product_title": product.title,
                        "sku_name": sku.name,
                        "requested_quantity": item.quantity,
                        "available_quantity": sku.active_quantity,
                    },
                }
            )
            continue
        if sku.active_quantity < item.quantity:
            issues.append(
                {
                    "cart_item_id": item.id,
                    "sku_id": item.sku_id,
                    "issue_type": "INSUFFICIENT_STOCK",
                    "severity": "warning",
                    "message": "Доступно меньше товара, чем в корзине",
                    "details": {
                        "product_id": product.id,
                        "product_title": product.title,
                        "sku_name": sku.name,
                        "requested_quantity": item.quantity,
                        "available_quantity": sku.active_quantity,
                    },
                }
            )

    return {
        "is_valid": not issues,
        "can_checkout": bool(items) and not any(issue["severity"] == "critical" for issue in issues),
        "total_items": len(items),
        "validation_timestamp": now_utc().isoformat(),
        "issues": issues,
    }


def build_similar_products(product: Product, all_products: list[Product], limit: int) -> list[Product]:
    candidates = [
        candidate
        for candidate in all_products
        if candidate.id != product.id and product_is_visible(candidate) and candidate.category_id == product.category_id
    ]
    candidates.sort(key=lambda item: (item.popularity, item.rating), reverse=True)
    if len(candidates) < limit and product.category and product.category.parent_id:
        sibling_candidates = [
            candidate
            for candidate in all_products
            if candidate.id != product.id
            and product_is_visible(candidate)
            and candidate.category
            and candidate.category.parent_id == product.category.parent_id
            and candidate.category_id != product.category_id
            and candidate not in candidates
        ]
        sibling_candidates.sort(key=lambda item: (item.popularity, item.rating), reverse=True)
        candidates.extend(sibling_candidates)
    return candidates[:limit]


def next_order_number(session: Session) -> int:
    max_number = session.scalar(select(func.max(Order.order_number)))
    return (max_number or 5000) + 1


def assert_product_exists(session: Session, product_id: str) -> Product:
    return get_product_or_404(session, product_id)


def find_cart_item(session: Session, item_id: str) -> CartItem | None:
    stmt = (
        select(CartItem)
        .options(
            joinedload(CartItem.sku).joinedload(Sku.product).joinedload(Product.store),
            joinedload(CartItem.sku).joinedload(Sku.product).joinedload(Product.category),
            joinedload(CartItem.sku).selectinload(Sku.images),
            joinedload(CartItem.sku).selectinload(Sku.characteristics),
            joinedload(CartItem.sku).joinedload(Sku.product).selectinload(Product.images),
            joinedload(CartItem.sku).joinedload(Sku.product).selectinload(Product.characteristics),
        )
        .where(CartItem.id == item_id)
    )
    return session.scalar(stmt)


def ensure_cart_item_owner(item: CartItem | None, user_id: str | None, session_id: str | None) -> CartItem:
    if item is None:
        raise APIError(404, "CART_ITEM_NOT_FOUND", "Позиция не найдена в корзине")
    if user_id and item.user_id == user_id:
        return item
    if session_id and item.session_id == session_id:
        return item
    raise APIError(403, "ACCESS_DENIED", "Нет доступа к этой позиции корзины")


def validate_sku_for_cart(sku: Sku, quantity: int) -> None:
    product = sku.product
    if product.is_deleted:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Товар не найден")
    if product.status == ProductStatus.BLOCKED or product.is_blocked:
        raise APIError(410, "SKU_NOT_AVAILABLE", "Товар недоступен для покупки")
    if product.status != ProductStatus.MODERATED:
        raise APIError(410, "PRODUCT_NOT_AVAILABLE", "Товар недоступен и не может быть обновлён")
    if not sku.is_active:
        raise APIError(410, "SKU_NOT_AVAILABLE", "Товар недоступен для покупки")
    if quantity > sku.active_quantity:
        raise APIError(422, "INSUFFICIENT_STOCK", f"Нельзя установить {quantity}, доступно только {sku.active_quantity}")


def add_or_update_cart_item(session: Session, sku_id: str, quantity: int, user_id: str | None, session_id: str | None) -> tuple[CartItem, int]:
    sku = get_sku_or_404(session, sku_id)
    validate_sku_for_cart(sku, quantity)

    stmt = select(CartItem).where(CartItem.sku_id == sku_id)
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    else:
        stmt = stmt.where(CartItem.session_id == session_id)
    existing = session.scalar(stmt)
    status_code = 201
    now = now_utc()
    if existing is not None:
        new_quantity = existing.quantity + quantity
        validate_sku_for_cart(sku, new_quantity)
        existing.quantity = new_quantity
        existing.updated_at = now
        item = existing
        status_code = 200
    else:
        item = CartItem(
            id=make_id(),
            user_id=user_id,
            session_id=session_id,
            sku_id=sku_id,
            quantity=quantity,
            created_at=now,
            updated_at=now,
        )
        session.add(item)

    session.commit()
    refreshed = find_cart_item(session, item.id)
    return ensure_cart_item_owner(refreshed, user_id, session_id), status_code


def update_cart_item_quantity(session: Session, item: CartItem, quantity: int) -> CartItem:
    validate_sku_for_cart(item.sku, quantity)
    item.quantity = quantity
    item.updated_at = now_utc()
    session.commit()
    refreshed = find_cart_item(session, item.id)
    return ensure_cart_item_owner(refreshed, item.user_id, item.session_id)


def checkout_cart(session: Session, user_id: str, idempotency_key: str | None = None) -> Order:
    if idempotency_key:
        existing_order = session.scalar(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id, Order.idempotency_key == idempotency_key)
        )
        if existing_order is not None:
            return existing_order

    cart_items = get_cart_items(session, user_id, None)
    if not cart_items:
        raise APIError(409, "CART_EMPTY", "Корзина пуста")

    validation = build_validation_response(cart_items)
    if not validation["can_checkout"]:
        raise APIError(409, "CHECKOUT_BLOCKED", "Корзина содержит недоступные товары", {"issues": validation["issues"]})

    locked_skus = {
        sku.id: sku
        for sku in session.scalars(select(Sku).where(Sku.id.in_([item.sku_id for item in cart_items])).with_for_update()).all()
    }
    for item in cart_items:
        locked_sku = locked_skus[item.sku_id]
        validate_sku_for_cart(locked_sku, item.quantity)

    now = now_utc()
    order = Order(
        id=make_id(),
        order_number=next_order_number(session),
        user_id=user_id,
        idempotency_key=idempotency_key,
        status=OrderStatus.PAID,
        total_amount=0,
        currency="RUB",
        reservation_released=False,
        created_at=now,
        updated_at=now,
        cancelled_at=None,
    )
    total_amount = 0
    for item in cart_items:
        sku = locked_skus[item.sku_id]
        product = sku.product
        sku.active_quantity -= item.quantity
        line_total = sku.price_cents * item.quantity
        total_amount += line_total
        order.items.append(
            OrderItem(
                id=make_id(),
                product_id=product.id,
                sku_id=sku.id,
                product_title=product.title,
                sku_name=sku.name,
                unit_price=sku.price_cents,
                quantity=item.quantity,
                line_total=line_total,
            )
        )
        session.delete(item)

    order.total_amount = total_amount
    session.add(order)
    session.commit()
    refreshed = session.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order.id))
    return refreshed


def cancel_order(session: Session, order: Order, reason: str | None = None) -> Order:
    if order.status not in CHECKOUT_CANCELABLE:
        raise APIError(409, "CANCEL_NOT_ALLOWED", "Заказ нельзя отменить на текущем статусе")

    if not order.reservation_released:
        sku_ids = [item.sku_id for item in order.items]
        sku_map = {sku.id: sku for sku in session.scalars(select(Sku).where(Sku.id.in_(sku_ids)).with_for_update()).all()}
        for item in order.items:
            sku_map[item.sku_id].active_quantity += item.quantity
        order.reservation_released = True

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now_utc()
    order.updated_at = now_utc()
    session.commit()
    return session.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order.id))


def send_b2b_fulfill(order: Order) -> bool:
    settings = get_settings()
    if not settings.b2b_base_url:
        return False

    payload = {
        "order_id": order.id,
        "items": [{"sku_id": item.sku_id, "quantity": item.quantity} for item in order.items],
    }
    try:
        response = httpx.post(
            f"{settings.b2b_base_url.rstrip('/')}/api/v1/fulfill",
            json=payload,
            headers=b2b_headers(),
            timeout=settings.b2b_timeout_seconds,
        )
    except httpx.RequestError:
        return False
    return response.status_code < 500


def mark_order_delivered(session: Session, order: Order) -> tuple[Order, bool]:
    order.status = OrderStatus.DELIVERED
    order.updated_at = now_utc()
    session.commit()

    refreshed = session.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order.id))
    fulfill_sent = send_b2b_fulfill(refreshed)
    return refreshed, fulfill_sent


def build_order_list_response(orders: list[Order], limit: int, offset: int) -> dict:
    total = len(orders)
    sliced = orders[offset : offset + limit]
    return {
        "total_count": total,
        "limit": limit,
        "offset": offset,
        "items": [serialize_order(order) for order in sliced],
    }


def demo_metadata() -> dict:
    settings = get_settings()
    return {"demo_user_id": settings.demo_user_id, "demo_session_id": settings.demo_session_id}


def pagination(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> tuple[int, int]:
    return limit, offset
