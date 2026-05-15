from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_search_returns_matching_products() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products?search=matcha")

    assert response.status_code == 200
    titles = [item["title"].lower() for item in response.json()["items"]]
    assert any("matcha" in title for title in titles)


def test_short_query_returns_400() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products?search=ab")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SEARCH"


def test_special_chars_do_not_break_query() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products?search=iPhone%2515%27")

    assert response.status_code == 200
    assert response.json()["items"] == []
