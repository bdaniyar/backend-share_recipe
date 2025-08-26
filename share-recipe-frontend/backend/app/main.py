import os

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from starlette.middleware.sessions import SessionMiddleware

from app.admin import setup_admin
from app.api import recipe as recipe_router
from app.api import token, user
from app.config.config import settings
from app.core.logging import setup_logging, RequestLoggingMiddleware
import logging

# Configure logging as early as possible
setup_logging()

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
