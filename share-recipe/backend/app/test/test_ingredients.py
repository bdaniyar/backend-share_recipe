import pytest

pytestmark = pytest.mark.asyncio


async def test_add_ingredient_validation_and_dedupe(auth_client, client):
    # Too short
    resp = await auth_client.post("/api/recipes/ingredients/", json={"name": "ab"})
    assert resp.status_code == 400
    assert "at least 3" in resp.json().get("detail", "")

    # Invalid chars
    resp = await auth_client.post("/api/recipes/ingredients/", json={"name": "sugar!"})
    assert resp.status_code == 400
    assert "only letters" in resp.json().get("detail", "")

    # Add fresh ingredient
    resp = await auth_client.post(
        "/api/recipes/ingredients/", json={"name": "Green onion"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["existing"] is False
    ing_id = data["id"]

    # Dedupe by normalized name (collapsed/lower)
    resp2 = await auth_client.post(
        "/api/recipes/ingredients/", json={"name": "  green   onion  "}
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["existing"] is True
    assert data2["id"] == ing_id

    # Search requires q; without q -> []
    resp = await client.get("/api/recipes/ingredients/")
    assert resp.status_code == 200
    assert resp.json() == []

    # Search by substring of normalized name
    resp = await client.get("/api/recipes/ingredients/", params={"q": "onion"})
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["id"] == ing_id and i["name"] == "Green onion" for i in items)
