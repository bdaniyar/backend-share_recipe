import pytest

pytestmark = pytest.mark.asyncio


async def _create_recipe(
    auth_client, title="Pasta", description="Simple", instructions="Boil"
):
    resp = await auth_client.post(
        "/api/recipes/create/",
        json={"title": title, "description": description, "instructions": instructions},
    )
    assert resp.status_code == 200
    return resp.json()


async def test_create_and_get_recipe_without_ingredients(auth_client, client):
    created = await _create_recipe(auth_client)
    rid = created["id"]

    # list public should include it for anonymous since include_self default False only for authed user
    resp = await client.get("/api/recipes/list/")
    assert resp.status_code == 200
    items = resp.json()
    assert any(r["id"] == rid for r in items)

    # get by id
    resp = await client.get(f"/api/recipes/recipe/{rid}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Pasta"
    assert data.get("ingredients") == [] or data.get("ingredients") is None


async def test_create_with_ingredients_and_filter(auth_client, client):
    # Create ingredients
    r1 = await auth_client.post("/api/recipes/ingredients/", json={"name": "Tomato"})
    r2 = await auth_client.post("/api/recipes/ingredients/", json={"name": "Basil"})
    i1 = r1.json()["id"]
    i2 = r2.json()["id"]

    # Create recipe with these ingredients
    resp = await auth_client.post(
        "/api/recipes/create/",
        json={
            "title": "Bruschetta",
            "description": "Tasty",
            "instructions": "Mix",
            "ingredients": [i1, i2],
        },
    )
    assert resp.status_code == 200
    recipe = resp.json()
    rid = recipe["id"]
    assert {ing["name"] for ing in recipe.get("ingredients", [])} == {"Tomato", "Basil"}

    # Filter by ingredients (one)
    list1 = await client.get("/api/recipes/list/", params={"ingredients": str(i1)})
    assert list1.status_code == 200
    items1 = list1.json()
    assert any(r["id"] == rid for r in items1)

    # Filter by both
    list2 = await client.get("/api/recipes/list/", params={"ingredients": f"{i1},{i2}"})
    assert list2.status_code == 200
    items2 = list2.json()
    assert any(r["id"] == rid for r in items2)


async def test_patch_and_delete_recipe(auth_client, client):
    recipe = await _create_recipe(auth_client, title="Soup")
    rid = recipe["id"]

    # Patch title
    resp = await auth_client.patch(
        f"/api/recipes/recipe/{rid}/", json={"title": "New Soup"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Soup"

    # Delete
    del_resp = await auth_client.delete(f"/api/recipes/recipe/{rid}/")
    assert del_resp.status_code == 200
    # Ensure gone
    get_resp = await client.get(f"/api/recipes/recipe/{rid}/")
    assert get_resp.status_code == 404


async def test_comments_flow(auth_client, client):
    recipe = await _create_recipe(auth_client, title="Cake")
    rid = recipe["id"]

    # No comments initially
    resp = await client.get(f"/api/recipes/recipe/{rid}/comments/")
    assert resp.status_code == 200
    assert resp.json() == []

    # Add a comment
    add = await auth_client.post(
        f"/api/recipes/recipe/{rid}/comments/", json={"content": "Nice"}
    )
    assert add.status_code == 200
    comment = add.json()

    # List contains it
    resp2 = await client.get(f"/api/recipes/recipe/{rid}/comments/")
    assert resp2.status_code == 200
    items = resp2.json()
    assert any(c["id"] == comment["id"] and c["username"] == "testuser" for c in items)

    # Reply
    add2 = await auth_client.post(
        f"/api/recipes/recipe/{rid}/comments/",
        json={"content": "Thanks", "parent_id": comment["id"]},
    )
    assert add2.status_code == 200
    reply = add2.json()
    assert reply["parent_id"] == comment["id"]


async def test_like_unlike_flow(auth_client):
    recipe = await _create_recipe(auth_client, title="LikeMe")
    rid = recipe["id"]

    # Like
    r1 = await auth_client.post(f"/api/recipes/recipe/{rid}/like/")
    assert r1.status_code == 200
    assert r1.json()["likes"] == 1

    # Like again idempotent
    r2 = await auth_client.post(f"/api/recipes/recipe/{rid}/like/")
    assert r2.status_code == 200
    assert r2.json()["likes"] == 1

    # Unlike
    r3 = await auth_client.delete(f"/api/recipes/recipe/{rid}/like/")
    assert r3.status_code == 200
    assert r3.json()["likes"] == 0


async def test_save_unsave_and_list_saved(auth_client):
    recipe = await _create_recipe(auth_client, title="SaveMe")
    rid = recipe["id"]

    s1 = await auth_client.post(f"/api/recipes/recipe/{rid}/save/")
    assert s1.status_code == 200
    assert s1.json()["saved"] is True

    # Saved list should contain the recipe
    ls = await auth_client.get("/api/recipes/saved/")
    assert ls.status_code == 200
    saved = ls.json()
    assert any(r["id"] == rid for r in saved)

    # Unsave
    s2 = await auth_client.delete(f"/api/recipes/recipe/{rid}/save/")
    assert s2.status_code == 200
    assert s2.json()["saved"] is False


async def test_my_recipes_and_public_exclusion(auth_client, client):
    r1 = await _create_recipe(auth_client, title="Mine1")
    r2 = await _create_recipe(auth_client, title="Mine2")

    # My recipes (auth)
    mine = await auth_client.get("/api/recipes/my-recipes/")
    assert mine.status_code == 200
    my_items = mine.json()
    ids = {r["id"] for r in my_items}
    assert {r1["id"], r2["id"]}.issubset(ids)

    # Public list as authenticated should exclude own posts by default
    public_authed = await auth_client.get("/api/recipes/list/")
    assert public_authed.status_code == 200
    pub_items = public_authed.json()
    pub_ids = {r["id"] for r in pub_items}
    assert r1["id"] not in pub_ids and r2["id"] not in pub_ids


async def test_patch_update_ingredients(auth_client):
    # Ingredients
    a = await auth_client.post("/api/recipes/ingredients/", json={"name": "Apple"})
    b = await auth_client.post("/api/recipes/ingredients/", json={"name": "Banana"})
    ia = a.json()["id"]
    ib = b.json()["id"]

    # Recipe with A
    recipe = await auth_client.post(
        "/api/recipes/create/",
        json={"title": "Fruit", "ingredients": [ia]},
    )
    assert recipe.status_code == 200
    data = recipe.json()
    rid = data["id"]
    assert [ing["name"] for ing in data.get("ingredients", [])] == ["Apple"]

    # Patch to B
    upd = await auth_client.patch(
        f"/api/recipes/recipe/{rid}/", json={"ingredients": [ib]}
    )
    assert upd.status_code == 200
    after = upd.json()
    assert [ing["name"] for ing in after.get("ingredients", [])] == ["Banana"]
