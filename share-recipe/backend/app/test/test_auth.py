# filepath: backend/app/test/test_auth.py
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.utils.security import ALGORITHM, SECRET_KEY, create_email_token

pytestmark = pytest.mark.asyncio


async def test_signup_requires_email_token(client):
    payload = {
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "StrongP@ssw0rd",
        "password2": "StrongP@ssw0rd",
    }
    resp = await client.post("/api/user/signup/", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "Email verification required" in data.get("detail", "")


async def test_signup_username_taken(client, test_user):
    email = "unique@example.com"
    token = create_email_token(email)
    headers = {"X-Email-Token": token}
    # username already exists from test_user fixture
    payload = {
        "email": email,
        "username": "testuser",
        "password": "StrongP@ssw0rd",
        "password2": "StrongP@ssw0rd",
    }
    resp = await client.post("/api/user/signup/", headers=headers, json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "Username already taken" in data.get("detail", "")


async def test_signup_email_already_registered(client, test_user):
    # try registering existing email of test_user
    email = test_user.email
    token = create_email_token(email)
    headers = {"X-Email-Token": token}
    payload = {
        "email": email,
        "username": "someoneelse",
        "password": "StrongP@ssw0rd",
        "password2": "StrongP@ssw0rd",
    }
    resp = await client.post("/api/user/signup/", headers=headers, json=payload)
    # Depending on model validation layer, this can be 400 from handler or 422 from Pydantic
    assert resp.status_code in (400, 422)


async def test_signup_success_then_signin(client):
    email = "okuser@example.com"
    token = create_email_token(email)
    headers = {"X-Email-Token": token}
    payload = {
        "email": email,
        "username": "okuser",
        "password": "StrongP@ssw0rd",
        "password2": "StrongP@ssw0rd",
    }
    resp = await client.post("/api/user/signup/", headers=headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email
    assert data["username"] == "okuser"

    # Now signin
    signin = await client.post(
        "/api/user/signin/",
        json={"email": email, "password": "StrongP@ssw0rd"},
    )
    assert signin.status_code == 200
    creds = signin.json()
    assert "access" in creds and "refresh" in creds


async def test_signin_wrong_email(client):
    resp = await client.post(
        "/api/user/signin/",
        json={"email": "nope@example.com", "password": "StrongP@ssw0rd"},
    )
    assert resp.status_code == 401
    assert resp.json().get("detail") == "Invalid email or password"


async def test_signin_wrong_password(client, test_user):
    resp = await client.post(
        "/api/user/signin/",
        json={"email": test_user.email, "password": "WrongPass1!"},
    )
    assert resp.status_code == 401
    assert resp.json().get("detail") == "Invalid email or password"


async def test_signin_success_returns_tokens(client, test_user):
    resp = await client.post(
        "/api/user/signin/",
        json={"email": test_user.email, "password": "StrongP@ssw0rd"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data and "refresh" in data


async def test_token_refresh_invalid(client):
    resp = await client.post(
        "/api/user/token/refresh/",
        json={"refresh": "not-a-valid-jwt"},
    )
    assert resp.status_code == 401
    assert resp.json().get("detail") == "Invalid refresh token"


async def test_token_refresh_expired(client, test_user):
    # Build an already expired refresh token
    payload = {
        "sub": str(test_user.id),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    resp = await client.post(
        "/api/user/token/refresh/",
        json={"refresh": expired},
    )
    assert resp.status_code == 401
    assert resp.json().get("detail") == "Invalid refresh token"


async def test_token_refresh_success(client, test_user):
    # Sign in to get a refresh token
    signin = await client.post(
        "/api/user/signin/",
        json={"email": test_user.email, "password": "StrongP@ssw0rd"},
    )
    assert signin.status_code == 200
    tokens = signin.json()
    refresh = tokens["refresh"]

    # Refresh
    resp = await client.post(
        "/api/user/token/refresh/",
        json={"refresh": refresh},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data and isinstance(data["access"], str)
