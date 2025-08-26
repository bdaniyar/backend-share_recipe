# routers/recipes.py
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.config import settings
from app.db.dao.ingredients import create_ingredient, search_ingredients
from app.db.dao.recipe import (
    add_comment,
    add_like,
    add_save,
    create_recipe,
    delete_recipe,
    get_recipe_by_id,
    get_recipes_by_user,
    list_comments,
    list_recipes,
    list_saved,
    remove_like,
    remove_save,
    set_recipe_image,
    update_recipe,
)
from app.db.database import User
from app.db.recipes import Recipe
from app.db.session import get_async_session
from app.models.recipe import (
    CommentResponse,
    RecipeCreate,
    RecipeResponse,
    RecipeUpdate,
)
from app.models.feedback import FeedbackCreate, FeedbackResponse
from app.db.dao.feedback import create_feedback, get_all_feedback
from app.services.auth import get_current_user, get_optional_user

# Root media dir (same logic as in main.py: share-recipe-frontend/media)
MEDIA_ROOT = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(__file__))
    ),  # -> share-recipe-frontend
    "media",
)

router = APIRouter(prefix="/api/recipes", tags=["Recipes"])


@router.post("/create/", response_model=RecipeResponse)
async def create_new_recipe(
    recipe: RecipeCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Daily posts limit per user
    try:
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        q = (
            select(func.count())
            .select_from(Recipe)
            .where(and_(Recipe.user_id == user.id, Recipe.created_at >= start_of_day))
        )
        res = await session.execute(q)
        count_today = int(res.scalar() or 0)
        if count_today >= int(getattr(settings, "POSTS_DAILY_LIMIT", 5)):
            raise HTTPException(
                status_code=429,
                detail=f"Daily post limit reached ({getattr(settings, 'POSTS_DAILY_LIMIT', 5)}). Try again tomorrow.",
            )
    except HTTPException:
        raise
    except Exception:
        # If counting fails for any reason, be permissive but log later
        pass

    return await create_recipe(recipe, user, session)


@router.get("/list/", response_model=list[RecipeResponse])
async def list_public_recipes(
    search: str | None = None,
    include_self: bool = False,
    ingredients: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(get_optional_user),
):
    # Parse comma-separated ingredient IDs
    ingredient_ids = None
    if ingredients:
        parsed: list[int] = []
        for part in ingredients.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                parsed.append(int(part))
            except Exception:
                continue
        ingredient_ids = parsed or None

    # user is optional; if present (authenticated), liked/saved flags will be included
    # DAO will exclude current user's own posts when user is provided unless include_self=True
    return await list_recipes(
        session, search, user, include_self, ingredient_ids=ingredient_ids
    )


@router.get("/my-recipes/", response_model=list[RecipeResponse])
async def list_my_recipes(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    return await get_recipes_by_user(user, session)


@router.get("/saved/", response_model=list[RecipeResponse])
async def list_saved_recipes(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    return await list_saved(user, session)


@router.get("/recipe/{recipe_id}/", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(get_optional_user),
):
    recipe = await get_recipe_by_id(recipe_id, session, user)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.patch("/recipe/{recipe_id}/", response_model=RecipeResponse)
async def patch_recipe(
    recipe_id: int,
    data: RecipeUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    recipe = await update_recipe(recipe_id, data, user, session)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found or forbidden")
    return recipe


@router.delete("/recipe/{recipe_id}/")
async def remove_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    ok = await delete_recipe(recipe_id, user, session)
    if not ok:
        raise HTTPException(status_code=404, detail="Recipe not found or forbidden")
    return {"status": "ok"}


@router.post("/recipe/{recipe_id}/image/")
async def upload_recipe_image(
    request: Request,
    recipe_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed.")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 10MB.")

    # Save into the mounted media directory so it is served by /media
    upload_dir = os.path.join(MEDIA_ROOT, "recipe_photos")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"recipe_{recipe_id}_{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    image_url = f"/media/recipe_photos/{filename}"
    recipe = await set_recipe_image(recipe_id, image_url, user, session)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found or forbidden")

    base_url = str(request.base_url).rstrip("/")
    return {"image_url": f"{base_url}{image_url}"}


@router.post("/recipe/{recipe_id}/like/")
async def like_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    count = await add_like(recipe_id, user, session)
    return {"likes": count}


@router.delete("/recipe/{recipe_id}/like/")
async def unlike_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    count = await remove_like(recipe_id, user, session)
    return {"likes": count}


@router.post("/recipe/{recipe_id}/save/")
async def save_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await add_save(recipe_id, user, session)
    return {"saved": True}


@router.delete("/recipe/{recipe_id}/save/")
async def unsave_recipe(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await remove_save(recipe_id, user, session)
    return {"saved": False}


@router.get("/recipe/{recipe_id}/comments/")
async def get_comments(
    recipe_id: int, session: AsyncSession = Depends(get_async_session)
):
    items = await list_comments(recipe_id, session)
    return [CommentResponse.model_validate(i) for i in items]


@router.post("/recipe/{recipe_id}/comments/")
async def post_comment(
    recipe_id: int,
    data: dict,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    content = (data or {}).get("content")
    parent_id = (data or {}).get("parent_id")  # allow reply
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Content is required")
    c = await add_comment(
        recipe_id, content.strip(), user, session, parent_id=parent_id
    )
    return CommentResponse.model_validate(c)


# Ingredients schemas
class IngredientIn(BaseModel):
    name: str


LETTERS_RE = re.compile(r"^[A-Za-zА-Яа-яЁё\s-]{3,}$")


def _normalize_ingredient(name: str) -> str:
    return " ".join(name.strip().lower().split())


@router.get("/ingredients/")
async def ingredients_search(
    q: str | None = None, session: AsyncSession = Depends(get_async_session)
):
    """Search ingredients by substring of normalized name."""
    if not q:
        # return a small list of popular or recent ingredients; for now, empty list
        return []
    items = await search_ingredients(session, q)
    return [{"id": i.id, "name": i.name} for i in items]


@router.post("/ingredients/")
async def ingredients_add(
    payload: IngredientIn,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """Add a new ingredient if it passes validation and doesn't already exist."""
    raw = (payload.name or "").strip()
    if len(raw) < 3:
        raise HTTPException(
            status_code=400, detail="Ingredient must be at least 3 characters"
        )
    if not LETTERS_RE.match(raw):
        raise HTTPException(
            status_code=400,
            detail="Ingredient must contain only letters, spaces or hyphens",
        )
    norm = _normalize_ingredient(raw)
    # Try to find existing via search (DAO will use norm like)
    from app.db.dao.ingredients import get_by_normalized

    existing = await get_by_normalized(session, norm)
    if existing:
        return {"id": existing.id, "name": existing.name, "existing": True}
    ing = await create_ingredient(session, raw)
    return {"id": ing.id, "name": ing.name, "existing": False}


@router.get("/options/")
async def get_options(session: AsyncSession = Depends(get_async_session)):
    # Fetch dynamic taxonomies (ingredients for now)
    from app.db.dao.ingredients import search_ingredients as _search

    items = await _search(session, q="", limit=50) if False else []
    # Placeholder taxonomy until implemented; ingredients will be fetched via separate search endpoint on UI
    return {
        "regions": [],
        "sessions": [],
        "types": [],
        "ingredients": [],
        "categories": [],
    }


@router.post("/feedback/", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """Submit user feedback"""
    feedback_record = await create_feedback(session, feedback.email, feedback.message)
    return FeedbackResponse.model_validate(feedback_record)


@router.get("/feedback/", response_model=List[FeedbackResponse])
async def list_feedback(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
):
    """List all feedback (admin only for now)"""
    # You can add role checking here if needed
    feedback_list = await get_all_feedback(session, limit, offset)
    return [FeedbackResponse.model_validate(f) for f in feedback_list]
