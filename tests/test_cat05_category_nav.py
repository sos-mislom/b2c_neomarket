from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Category
from app.seed import stable_uuid
from app.services import now_utc


def test_category_tree_returns_nested_structure() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/categories")

    assert response.status_code == 200
    roots = response.json()["items"]
    assert roots
    assert any(root["children"] for root in roots)


def test_breadcrumbs_return_path_from_root() -> None:
    category_id = stable_uuid("category:green-tea")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/breadcrumbs?category_id={category_id}")

    assert response.status_code == 200
    crumbs = response.json()["data"]
    assert crumbs[-1]["id"] == category_id
    assert all(crumb["url"].startswith("/catalog/") for crumb in crumbs)


def test_unknown_category_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/categories/unknown-category")

    assert response.status_code == 404


def test_ambiguous_params_returns_400() -> None:
    category_id = stable_uuid("category:green-tea")
    product_id = stable_uuid("product:sencha-yabukita-premium")

    with TestClient(app) as client:
        response = client.get(f"/api/v1/catalog/breadcrumbs?category_id={category_id}&product_id={product_id}")

    assert response.status_code == 400
    assert response.json()["code"] == "ambiguous_param"


def test_orphan_node_returns_422() -> None:
    orphan_id = stable_uuid("category:orphan")
    now = now_utc()
    with SessionLocal() as session:
        session.add(
            Category(
                id=orphan_id,
                name="Orphan",
                slug="orphan",
                description="Broken hierarchy fixture",
                parent_id="missing-parent",
                seo_title="Orphan",
                seo_description="Broken hierarchy fixture",
                seo_keywords=[],
                meta_tags={},
                image_url=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/catalog/breadcrumbs?category_id={orphan_id}")
    finally:
        with SessionLocal() as session:
            category = session.get(Category, orphan_id)
            if category is not None:
                session.delete(category)
                session.commit()

    assert response.status_code == 422
    assert response.json()["code"] == "orphan_node"
