from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_active_banners_returned_sorted_by_priority() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/home/banners")

    assert response.status_code == 200
    priorities = [item["priority"] for item in response.json()["items"]]
    assert priorities == sorted(priorities)


def test_no_active_banners_returns_200_empty() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/home/banners")

    assert response.status_code == 200
    assert "items" in response.json()


def test_click_on_unknown_banner_returns_400() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/banner-events",
            json={
                "events": [
                    {
                        "banner_id": "unknown-banner",
                        "event": "click",
                        "timestamp": "2026-05-15T12:00:00Z",
                    }
                ]
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "BANNER_NOT_FOUND"
