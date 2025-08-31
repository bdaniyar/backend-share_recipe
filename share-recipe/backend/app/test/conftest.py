# Test configuration and fixtures for FastAPI backend
# - Creates an isolated async SQLite database per test
# - Overrides get_async_session to use the test session
# - Provides httpx.AsyncClient without running app startup (avoids Redis requirement)
# - Provides an authorized client fixture that bypasses JWT and returns a test user

import os
import typing as t

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base

# Import all models so metadata knows about tables
from app.db.database import User  # noqa: F401
from app.db.ingredients import Ingredient  # noqa: F401
from app.db.recipe_ingredients import RecipeIngredient  # noqa: F401
from app.db.recipes import Recipe  # noqa: F401
from app.db.session import get_async_session
from app.db.social import Comment, RecipeLike, SavedRecipe  # noqa: F401
from app.utils.security import hash_password

# Ensure env defaults for tests before importing app/config
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
# Provide defaults for all required Settings fields to avoid ValidationError at import
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_PORT", "25")
os.environ.setdefault("SMTP_USER", "user")
os.environ.setdefault("SMTP_PASSWORD", "pass")
os.environ.setdefault("EMAIL_FROM", "test@example.com")
os.environ.setdefault("OAUTH_GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("OAUTH_GOOGLE_CLIENT_SECRET", "test-client-secret")


@pytest.fixture()
async def engine(tmp_path) -> t.AsyncIterator[AsyncEngine]:
    # Create a file-based SQLite DB per test for isolation
    db_file = tmp_path / "test.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    # Also reflect into settings for any code that reads DATABASE_URL dynamically
    os.environ["DATABASE_URL"] = test_db_url
    engine = create_async_engine(test_db_url, echo=False, future=True)
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        # Drop all tables and dispose engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture()
async def session(engine: AsyncEngine) -> t.AsyncIterator[AsyncSession]:
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest.fixture()
async def app_with_overrides(engine: AsyncEngine):
    # Import here so env is already set up
    from app.main import app as fastapi_app  # noqa

    # Disable startup/shutdown events (e.g., Redis init) for tests
    # FastAPI stores old-style events on router
    fastapi_app.router.on_startup.clear()
    fastapi_app.router.on_shutdown.clear()

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Also ensure any DAO that opens its own session uses the test engine
    import app.db.session as session_module

    original_session_maker = session_module.async_session_maker
    session_module.async_session_maker = SessionLocal

    async def _override_get_async_session() -> t.AsyncIterator[AsyncSession]:
        async with SessionLocal() as s:
            yield s

    fastapi_app.dependency_overrides[get_async_session] = _override_get_async_session
    try:
        yield fastapi_app
    finally:
        fastapi_app.dependency_overrides.pop(get_async_session, None)
        # Restore original session maker
        import app.db.session as session_module2

        session_module2.async_session_maker = original_session_maker


@pytest.fixture()
async def client(app_with_overrides):
    import httpx

    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture()
async def test_user(session: AsyncSession) -> User:
    # Minimal valid user for ownership/auth in tests
    u = User(
        email="user@example.com",  # use valid domain so EmailStr accepts it
        username="testuser",
        hashed_password=hash_password("StrongP@ssw0rd"),
        is_active=True,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest.fixture()
async def auth_client(app_with_overrides, test_user: User):
    # Override get_current_user and get_optional_user to bypass JWT in tests
    from fastapi import Request

    from app.services.auth import get_current_user, get_optional_user

    async def _override_get_current_user():
        return test_user

    async def _override_get_optional_user(request: Request):
        # Only treat as authenticated when special test header is present
        if request.headers.get("X-Test-Auth") == "1":
            return test_user
        return None

    app_with_overrides.dependency_overrides[get_current_user] = (
        _override_get_current_user
    )
    app_with_overrides.dependency_overrides[get_optional_user] = (
        _override_get_optional_user
    )

    import httpx

    transport = httpx.ASGITransport(app=app_with_overrides)
    # Inject header so this client is considered authenticated for optional auth
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Test-Auth": "1"}
    ) as c:
        try:
            yield c
        finally:
            app_with_overrides.dependency_overrides.pop(get_current_user, None)
            app_with_overrides.dependency_overrides.pop(get_optional_user, None)
