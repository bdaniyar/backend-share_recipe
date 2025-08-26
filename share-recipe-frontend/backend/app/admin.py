from __future__ import annotations

import os

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from starlette.requests import Request

from app.config.config import settings
from app.db.database import User
from app.db.feedback import Feedback
from app.db.ingredients import Ingredient
from app.db.recipes import Recipe
from app.db.social import Comment, RecipeLike, SavedRecipe


class SimpleAuth(AuthenticationBackend):
    def __init__(self, secret_key: str) -> None:
        super().__init__(secret_key=secret_key)

    async def login(self, request: Request) -> bool:  # type: ignore[override]
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        if username == os.getenv("ADMIN_USERNAME") and password == os.getenv(
            "ADMIN_PASSWORD"
        ):
            request.session.update({"admin": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:  # type: ignore[override]
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:  # type: ignore[override]
        return bool(request.session.get("admin"))


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = ["id", "email", "username", "is_active", "joined"]
    column_searchable_list = ["email", "username"]


class RecipeAdmin(ModelView, model=Recipe):
    name = "Recipe"
    name_plural = "Recipes"
    icon = "fa-solid fa-bowl-food"
    column_list = ["id", "title", "user_id", "created_at", "is_published"]
    column_searchable_list = ["title"]


class IngredientAdmin(ModelView, model=Ingredient):
    name = "Ingredient"
    name_plural = "Ingredients"
    icon = "fa-solid fa-carrot"
    column_list = ["id", "name"]
    column_searchable_list = ["name"]


class CommentAdmin(ModelView, model=Comment):
    name = "Comment"
    name_plural = "Comments"
    icon = "fa-solid fa-comments"
    column_list = ["id", "recipe_id", "user_id", "content", "created_at"]


class RecipeLikeAdmin(ModelView, model=RecipeLike):
    name = "Like"
    name_plural = "Likes"
    icon = "fa-solid fa-thumbs-up"
    column_list = ["id", "recipe_id", "user_id"]


class SavedRecipeAdmin(ModelView, model=SavedRecipe):
    name = "Saved"
    name_plural = "Saved Recipes"
    icon = "fa-solid fa-bookmark"
    column_list = ["id", "recipe_id", "user_id"]


class FeedbackAdmin(ModelView, model=Feedback):
    name = "Feedback"
    name_plural = "Feedback"
    icon = "fa-solid fa-comment"
    column_list = ["id", "email", "message", "created_at"]
    column_searchable_list = ["email", "message"]
    column_sortable_list = ["id", "email", "created_at"]


def _build_sync_engine(async_url: str):
    url = make_url(async_url)
    drv = url.drivername
    if "+aiosqlite" in drv:
        url = url.set(drivername="sqlite")
    elif "+asyncpg" in drv:
        url = url.set(drivername="postgresql+psycopg2")
    elif "+psycopg" in drv:
        url = url.set(drivername="postgresql+psycopg2")
    elif "+aiomysql" in drv:
        url = url.set(drivername="mysql+pymysql")
    else:
        # Fallback: strip async driver part
        url = url.set(drivername=drv.split("+")[0])
    return create_engine(url)


def setup_admin(app):
    # Build a real sync engine for SQLAdmin to avoid MissingGreenlet with async drivers
    sync_engine = _build_sync_engine(settings.DATABASE_URL)
    admin = Admin(
        app,
        sync_engine,
        base_url="/admin",
        authentication_backend=SimpleAuth(
            secret_key=os.getenv("SESSION_SECRET", settings.SECRET_KEY)
        ),
    )
    # Register views
    admin.add_view(UserAdmin)
    admin.add_view(RecipeAdmin)
    admin.add_view(IngredientAdmin)
    admin.add_view(CommentAdmin)
    admin.add_view(RecipeLikeAdmin)
    admin.add_view(SavedRecipeAdmin)
    admin.add_view(FeedbackAdmin)
    return admin
