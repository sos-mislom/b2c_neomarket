from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import stable_uuid


def test_add_to_favorites_returns_201() -> None:
    product_id = stable_uuid("product:longjing-spring-reserve")

    with TestClient(app) as client:
        response = client.post(f"/api/v1/favorites/{product_id}", headers={"X-User-Id": "favorite-user"})

    assert response.status_code == 201
    assert response.json()["product_id"] == product_id


def test_repeat_add_returns_200_not_duplicate() -> None:
    product_id = stable_uuid("product:gyokuro-asahi-shade")
    headers = {"X-User-Id": "repeat-favorite-user"}

    with TestClient(app) as client:
        first = client.post(f"/api/v1/favorites/{product_id}", headers=headers)
        second = client.post(f"/api/v1/favorites/{product_id}", headers=headers)
        listed = client.get("/api/v1/favorites", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert [item["product"]["id"] for item in listed.json()["items"]].count(product_id) == 1


def test_blocked_product_excluded_from_list() -> None:
    blocked_product_id = stable_uuid("product:tea-sampler-weekend-market")

    with TestClient(app) as client:
        response = client.get("/api/v1/favorites", headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"})

    assert response.status_code == 200
    assert blocked_product_id not in {item["product"]["id"] for item in response.json()["items"]}


def test_user_id_from_query_is_ignored() -> None:
    product_id = stable_uuid("product:darjeeling-first-flush")
    owner_id = "favorite-owner-user"
    attacker_id = "favorite-attacker-user"

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/favorites/{product_id}?user_id={attacker_id}",
            headers={"X-User-Id": owner_id},
        )
        owner_response = client.get(
            f"/api/v1/favorites?user_id={attacker_id}",
            headers={"X-User-Id": owner_id},
        )
        attacker_response = client.get("/api/v1/favorites", headers={"X-User-Id": attacker_id})

    assert response.status_code == 201
    assert response.json()["user_id"] == owner_id
    assert product_id in {item["product"]["id"] for item in owner_response.json()["items"]}
    assert product_id not in {item["product"]["id"] for item in attacker_response.json()["items"]}
