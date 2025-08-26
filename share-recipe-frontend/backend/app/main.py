import os

import redis.asyncio as redis
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from starlette.middleware.sessions import SessionMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.admin import setup_admin
from app.api import recipe as recipe_router
from app.api import token, user
from app.config.config import settings
from app.core.logging import setup_logging, RequestLoggingMiddleware
import logging

# Configure logging as early as possible
setup_logging()

ENV = os.getenv("ENV", "development").lower()

# Disable automatic docs in production (we will add protected endpoints manually)
if ENV == "production":
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
else:
    app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Create media directory relative to the backend directory
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# Enable server-side sessions for admin auth
app.add_middleware(
    SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", settings.SECRET_KEY)
)

app.include_router(user.router)
app.include_router(token.router)
app.include_router(recipe_router.router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://frontend-share-recipe-for-vercel.vercel.app",
    ],  # allow common Next.js dev ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

# HTTP Basic security for docs
security = HTTPBasic()


def _docs_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if ENV != "production":  # No protection in non-production
        return True
    username_ok = os.getenv("DOCS_USERNAME")
    password_ok = os.getenv("DOCS_PASSWORD")
    if not (
        credentials.username == username_ok and credentials.password == password_ok
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# Protected docs (only created in production; harmless in dev if duplicates of defaults)
if ENV == "production":
    from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
    from fastapi.responses import JSONResponse

    @app.get("/openapi.json", dependencies=[Depends(_docs_auth)])
    async def openapi_json():
        return JSONResponse(app.openapi())

    @app.get("/docs", dependencies=[Depends(_docs_auth)])
    async def swagger_ui():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="API Docs")

    @app.get("/redoc", dependencies=[Depends(_docs_auth)])
    async def redoc_ui():
        return get_redoc_html(openapi_url="/openapi.json", title="API Docs")


@app.on_event("startup")
async def startup():
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=False
    )
    FastAPICache.init(RedisBackend(redis_client), prefix="cache")
    # Mount SQLAdmin
    setup_admin(app)


@app.on_event("startup")
async def _on_startup():
    logging.getLogger(__name__).info("Application startup")


@app.on_event("shutdown")
async def _on_shutdown():
    logging.getLogger(__name__).info("Application shutdown")
