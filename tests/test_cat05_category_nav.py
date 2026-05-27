from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Category
from app.seed import stable_uuid
from app.services import now_utc


def test_categories_return_flat_category_refs() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/categories")

    assert response.status_code == 200
    categories = response.json()
    assert isinstance(categories, list)
    assert categories
    assert all("children" not in category for category in categories)
    assert {"id", "name", "slug", "parent_id", "level", "path"} <= set(categories[0])
    assert all(isinstance(category["path"], list) for category in categories)
    assert all(category["path"][-1] == category["slug"] for category in categories)
    assert all(len(category["path"]) == category["level"] + 1 for category in categories)


def test_category_tree_returns_nested_structure() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/categories/tree")

    assert response.status_code == 200
    roots = response.json()
    assert isinstance(roots, list)
    assert roots
    assert any(root["children"] for root in roots)
    assert {"id", "name", "slug", "parent_id", "level", "path", "children"} <= set(roots[0])
    assert isinstance(roots[0]["path"], list)
    assert roots[0]["path"][-1] == roots[0]["slug"]


def test_inactive_categories_not_visible() -> None:
    inactive_id = stable_uuid("category:inactive-hidden")
    now = now_utc()
    with SessionLocal() as session:
        session.add(
            Category(
                id=inactive_id,
                name="Inactive Hidden",
                slug="inactive-hidden",
                description="Hidden category fixture",
                parent_id=None,
                seo_title="Inactive Hidden",
                seo_description="Hidden category fixture",
                seo_keywords=[],
                meta_tags={},
                image_url=None,
                is_active=False,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/catalog/categories")
            tree_response = client.get("/api/v1/catalog/categories/tree")
    finally:
        with SessionLocal() as session:
            category = session.get(Category, inactive_id)
            if category is not None:
                session.delete(category)
                session.commit()

    assert list_response.status_code == 200
    assert inactive_id not in {category["id"] for category in list_response.json()}
    assert tree_response.status_code == 200
    assert inactive_id not in {category["id"] for category in tree_response.json()}


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
