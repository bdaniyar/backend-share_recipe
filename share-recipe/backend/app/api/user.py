# app/routes/user.py

import asyncio

# PKCE helpers
import base64
import hashlib
import json as jsonlib
import os
import random
import re
import secrets

# Add SSL and optional httpx/certifi imports
import ssl
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.config import settings
from app.db.dao.dao import UserDAO
from app.db.database import User
from app.db.session import get_async_session
from app.models.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RequestCodePayload,
    VerifyEmailRequest,
)
from app.models.user import (  # added import
    UserProfile,
    UserPublicProfile,
    UserSignIn,
    UserSignup,
    UserUpdate,
)
from app.services.auth import (  # ensure get_optional_user imported
    get_current_user,
    get_optional_user,
)
from app.utils.mailer import send_verification_code
from app.utils.security import (
    create_access_token,
    create_email_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - optional
    httpx = None  # type: ignore
try:
    import certifi  # type: ignore
except Exception:  # pragma: no cover - optional
    certifi = None  # type: ignore
from app.db.dao.recipe import get_recipes_by_user, list_saved  # added imports

# Cooldown for username changes (e.g., 14 days)
USERNAME_CHANGE_COOLDOWN_DAYS = 3

router = APIRouter(prefix="/api/user", tags=["User"])


@router.post("/request-code/")
async def request_code(payload: RequestCodePayload):
    email = payload.email
    r = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True
    )
    # Rate limit: max 3 codes per 5 minutes per email
    count_key = f"verify_count:{email}"
    code_key = f"verify:{email}"
    count = await r.get(count_key)
    if count is not None and int(count) >= 3:
        raise HTTPException(
            status_code=429,
            detail="You can request a verification code no more than 3 times in 5 minutes. Please wait before trying again.",
        )
    # Generate 6-digit code
    code = f"{random.randint(0, 999999):06d}"
    # Save code to Redis with TTL 5 minutes
    await r.set(code_key, code, ex=300)
    # Increment count, set TTL if new
    pipe = r.pipeline()
    pipe.incr(count_key)
    pipe.expire(count_key, 300)
    await pipe.execute()
    # Send email
    await send_verification_code(email, code)
    return {"detail": "Verification code sent"}


@router.post("/verify-code/")
async def verify_email_code(data: VerifyEmailRequest):
    r = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True
    )
    key = f"verify:{data.email}"
    stored = await r.get(key)
    if not stored or stored != data.code:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    await r.delete(key)
    # Issue a short-lived token confirming email verification
    token = create_email_token(data.email)
    return {"token": token}


@router.post("/signup/")
async def signup(
    user_data: UserSignup,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    # Require verified email token
    email_token = request.headers.get("x-email-token") or request.headers.get(
        "X-Email-Token"
    )
    if not email_token:
        raise HTTPException(status_code=400, detail="Email verification required")
    try:
        payload = jwt.decode(
            email_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("type") != "email" or payload.get("sub") != user_data.email:
            raise HTTPException(
                status_code=400, detail="Invalid email verification token"
            )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid email verification token")

    # Email uniqueness
    existing_user = await UserDAO.get_user_by_email(session, user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Username policy and uniqueness
    if not re.fullmatch(r"^[A-Za-z0-9._]{3,20}$", user_data.username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-20 chars: letters, digits, dots, underscores.",
        )
    existing_user = await UserDAO.get_user_by_username(session, user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Password match and strength
    if user_data.password != user_data.password2:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if (
        not re.search(r"[A-Z]", user_data.password)
        or not re.search(r"[0-9]", user_data.password)
        or not re.search(r"[^A-Za-z0-9]", user_data.password)
        or len(user_data.password) < 8
    ):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 chars and include an uppercase letter, a digit, and a special character.",
        )

    # Create user
    user = await UserDAO.create_user(
        session,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
    )
    return {"id": user.id, "email": user.email, "username": user.username}


@router.post("/signin/")
async def signin(
    user_data: UserSignIn, session: AsyncSession = Depends(get_async_session)
):
    user = await UserDAO.get_user_by_email(session, user_data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Получаем строковое значение хеша пароля
    hashed_password = user.hashed_password
    if hasattr(hashed_password, "default") or str(type(hashed_password)).endswith(
        "Column"
    ):
        hashed_password = user.__dict__.get("hashed_password")
    if not isinstance(hashed_password, str):
        raise HTTPException(
            status_code=500, detail="User hashed_password is not a string."
        )
    if not verify_password(user_data.password, hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = getattr(user, "id", None)
    if user_id is None or not isinstance(user_id, int):
        raise HTTPException(
            status_code=500, detail="User id is not available or invalid."
        )

    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return {"access": access_token, "refresh": refresh_token}


@router.get("/profile/", response_model=UserProfile)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/profile/", response_model=UserProfile)
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    # Validate first and last names: 2-20 letters (spaces/hyphens allowed), capitalized
    def _valid_name(name: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-zА-Яа-яЁё\-\s]{2,20}", name))

    updates = user_update.model_dump(exclude_unset=True)

    # Bio optional: limit length, allow emojis/links; strip dangerous control chars
    if "bio" in updates and updates["bio"] is not None:
        bio = updates["bio"].strip()
        if len(bio) > 300:
            raise HTTPException(
                status_code=400, detail="Bio must be 300 characters or less."
            )
        # basic sanitize of control chars
        updates["bio"] = "".join(ch for ch in bio if ch >= " " or ch == "\n")

    if "first_name" in updates and updates["first_name"] is not None:
        if not _valid_name(updates["first_name"]):
            raise HTTPException(
                status_code=400,
                detail="First name must be 2-20 letters and may include spaces or hyphens.",
            )
        if not updates["first_name"][0].isupper():
            raise HTTPException(
                status_code=400, detail="First name must start with a capital letter."
            )

    if "last_name" in updates and updates["last_name"] is not None:
        if not _valid_name(updates["last_name"]):
            raise HTTPException(
                status_code=400,
                detail="Last name must be 2-20 letters and may include spaces or hyphens.",
            )
        if not updates["last_name"][0].isupper():
            raise HTTPException(
                status_code=400, detail="Last name must start with a capital letter."
            )

    # Username changes: regex, uniqueness, cooldown
    if (
        "username" in updates
        and updates["username"]
        and updates["username"] != current_user.username
    ):
        new_username = updates["username"]
        if not re.fullmatch(r"^[A-Za-z0-9._]{3,20}$", new_username):
            raise HTTPException(
                status_code=400,
                detail="Username must be 3-20 chars: letters, digits, dots, underscores.",
            )
        # Cooldown check (assumes we store last change date; if not present, allow and set now)
        last_changed = getattr(current_user, "username_changed_at", None)
        if last_changed is not None:
            if datetime.now(timezone.utc) - last_changed < timedelta(
                days=USERNAME_CHANGE_COOLDOWN_DAYS
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"You can change your username only once every {USERNAME_CHANGE_COOLDOWN_DAYS} days.",
                )
        setattr(current_user, "username", new_username)
        setattr(current_user, "username_changed_at", datetime.now(timezone.utc))
        updates.pop("username", None)

    for field, value in updates.items():
        setattr(current_user, field, value)

    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.post("/profile/photo/")
async def upload_profile_photo(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    # Валидация типа файла (только изображения)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed.")
    # Валидация размера файла (до 5 МБ)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 5MB.")
    # Сохраняем файл в папку media/profile_photos
    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # .../backend/app
        "..",  # go up from backend/ to share-recipe-frontend/
        "media",
        "profile_photos",
    )
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"user_{current_user.id}_{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(contents)
    # Сохраняем ссылку в базе
    setattr(current_user, "photo_url", f"/media/profile_photos/{filename}")
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    # Build absolute URL from request
    base_url = str(request.base_url).rstrip("/")
    absolute_url = f"{base_url}{current_user.photo_url}"
    return {"photo_url": absolute_url}


@router.delete("/profile/photo/")
async def delete_profile_photo(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    # Удаляем файл если есть
    if getattr(current_user, "photo_url", None):
        file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "..",
            str(current_user.photo_url).lstrip("/"),
        )
        if os.path.exists(file_path):
            os.remove(file_path)
        # Присваиваем None через setattr для Column[str | None]
        setattr(current_user, "photo_url", None)
        session.add(current_user)
        await session.commit()
        await session.refresh(current_user)
    return JSONResponse(content={"photo_url": None, "message": "Profile photo removed"})


@router.get("/oauth/google/login")
async def google_oauth_login(request: Request, next: str | None = None):
    """Redirects the user to Google OAuth consent screen."""
    client_id = settings.OAUTH_GOOGLE_CLIENT_ID
    # Build redirect URI based on current request base URL
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/user/oauth/google/callback"

    # Generate PKCE code_verifier and code_challenge
    # verifier: 43-128 chars, URL-safe
    verifier_bytes = secrets.token_bytes(64)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode().rstrip("=")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    # Create a signed state token carrying the next URL and PKCE verifier, expires in 5 minutes
    try:
        state_payload = {
            "type": "oauth_state",
            "next": next or "http://localhost:3000/oauth/google",
            "code_verifier": code_verifier,
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        }
        state_token = jwt.encode(
            state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        params["state"] = state_token
    except Exception:
        # Fallback to plain next only if encoding fails (dev only)
        if next:
            params["state"] = next

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    )
    return RedirectResponse(google_auth_url, status_code=302)


async def _exchange_code_for_tokens(
    code: str, redirect_uri: str, code_verifier: str | None = None
) -> dict:
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.OAUTH_GOOGLE_CLIENT_ID,
        "client_secret": settings.OAUTH_GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier
    # Prefer httpx which bundles certifi, fallback to urllib with certifi context
    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            # Fall back to urllib below
            pass
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Build SSL context with certifi if available
    context = None
    if certifi is not None:
        try:
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = None
    # Perform request in thread to keep async endpoint non-blocking
    if context is not None:
        resp = await asyncio.to_thread(urllib.request.urlopen, req, context=context)
    else:
        resp = await asyncio.to_thread(urllib.request.urlopen, req)
    body = await asyncio.to_thread(resp.read)
    return jsonlib.loads(body.decode())


async def _fetch_google_userinfo(access_token: str) -> dict:
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    # Prefer httpx which bundles certifi, fallback to urllib with certifi context
    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            # Fall back to urllib below
            pass
    req = urllib.request.Request(
        userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
    )
    context = None
    if certifi is not None:
        try:
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = None
    if context is not None:
        resp = await asyncio.to_thread(urllib.request.urlopen, req, context=context)
    else:
        resp = await asyncio.to_thread(urllib.request.urlopen, req)
    body = await asyncio.to_thread(resp.read)
    return jsonlib.loads(body.decode())


def _sanitize_username(base: str) -> str:
    # allow only letters, digits, dot and underscore; trim to 20
    cleaned = re.sub(r"[^A-Za-z0-9._]", "", base)
    if not cleaned:
        cleaned = "user"
    return cleaned[:20]


@router.get("/oauth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/user/oauth/google/callback"

    # Extract PKCE verifier (if present) from signed state
    code_verifier: str | None = None
    next_url_default = "http://localhost:3000/oauth/google"
    if state:
        try:
            decoded = jwt.decode(
                state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            if decoded.get("type") == "oauth_state":
                code_verifier = decoded.get("code_verifier")
                next_url_default = decoded.get("next", next_url_default)
        except Exception:
            # ignore invalid state
            pass

    try:
        tokens = await _exchange_code_for_tokens(
            code, redirect_uri, code_verifier=code_verifier
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {e}")

    access_token_google = tokens.get("access_token")
    if not access_token_google:
        raise HTTPException(status_code=400, detail="Missing access token from Google")

    try:
        guser = await _fetch_google_userinfo(access_token_google)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to fetch Google user info: {e}"
        )

    email = guser.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    # Find or create user
    existing = await UserDAO.get_user_by_email(session, email)
    if not existing:
        # Create a username from email local-part
        local = email.split("@")[0]
        base_username = _sanitize_username(local)
        username = base_username
        # Ensure uniqueness
        suffix = 0
        while await UserDAO.get_user_by_username(session, username):
            suffix += 1
            suffix_str = str(suffix)
            username = (base_username[: max(1, 20 - len(suffix_str))] + suffix_str)[:20]
        # Random strong password
        random_pw = secrets.token_urlsafe(16)
        user = await UserDAO.create_user(
            session, username=username, email=email, password=random_pw
        )
    else:
        user = existing

    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        raise HTTPException(status_code=500, detail="Invalid user id")

    # Issue our tokens
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)

    # Determine next URL from signed state (fallback to default)
    next_url = next_url_default
    if state:
        try:
            decoded = jwt.decode(
                state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            if decoded.get("type") == "oauth_state":
                next_url = decoded.get("next", next_url)
        except Exception:
            # ignore invalid state, use default
            pass

    # Append tokens as query params
    parsed = urllib.parse.urlparse(next_url)
    q = dict(urllib.parse.parse_qsl(parsed.query))
    q.update({"access": access, "refresh": refresh})
    new_query = urllib.parse.urlencode(q)
    final_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
    return RedirectResponse(final_url, status_code=302)


@router.get("/public/{username}", response_model=UserPublicProfile)
async def public_profile(
    username: str,
    session: AsyncSession = Depends(get_async_session),
    current: User | None = Depends(get_optional_user),
):
    user_obj = await UserDAO.get_user_by_username(session, username)
    if user_obj is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Get plain values (avoid Column objects)
    data = user_obj.__dict__
    recs = await get_recipes_by_user(user_obj, session)
    recs = [r for r in recs if getattr(r, "is_published", True)]
    saved = []
    if current is not None and getattr(current, "id", None) == getattr(
        user_obj, "id", None
    ):
        saved = await list_saved(user_obj, session)
    profile = UserPublicProfile(
        username=str(data.get("username")),
        first_name=data.get("first_name") or None,
        last_name=data.get("last_name") or None,
        joined=data.get("joined") or None,
        photo_url=data.get("photo_url") or None,
        bio=data.get("bio") or None,
        recipes=recs,
        saved_recipes=saved,
    )
    return profile


@router.post("/request-password-reset/")
async def request_password_reset(payload: PasswordResetRequest):
    email = payload.email.lower().strip()
    r = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True
    )
    code = f"{random.randint(100000, 999999)}"
    key = f"reset:{email}"
    await r.setex(key, 300, code)  # 5 minutes
    try:
        await send_verification_code(email, code)
    except Exception:
        # do not leak whether email exists; still report ok
        pass
    return {"status": "ok"}


@router.post("/reset-password/")
async def reset_password(
    data: PasswordResetConfirm, session: AsyncSession = Depends(get_async_session)
):
    email = data.email.lower().strip()
    # Verify code
    r = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True
    )
    stored = await r.get(f"reset:{email}")
    if not stored or stored != data.code:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Validate passwords
    if data.new_password != data.password2:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    import re as _re

    if (
        not _re.search(r"[A-Z]", data.new_password)
        or not _re.search(r"[0-9]", data.new_password)
        or not _re.search(r"[^A-Za-z0-9]", data.new_password)
        or len(data.new_password) < 8
    ):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 chars and include an uppercase letter, a digit, and a special character.",
        )

    # Update user password if user exists
    user = await UserDAO.get_user_by_email(session, email)
    if user:
        new_hash = hash_password(data.new_password)
        # Write to correct column name
        setattr(user, "hashed_password", new_hash)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    await r.delete(f"reset:{email}")
    return {"status": "ok"}
