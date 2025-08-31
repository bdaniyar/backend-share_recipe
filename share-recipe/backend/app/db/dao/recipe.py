# services/recipe.py
from typing import Optional, Sequence

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.database import User
from app.db.ingredients import Ingredient

# Import join table and Ingredient for lookups
from app.db.recipe_ingredients import RecipeIngredient
from app.db.recipes import Recipe
from app.db.social import Comment, RecipeLike, SavedRecipe
from app.models.recipe import IngredientOut, RecipeCreate, RecipeUpdate


# Helper to attach social fields
async def _attach_social_fields(
    db: AsyncSession, recipe: Recipe, user: Optional[User] = None
):
    # likes count
    cnt_res = await db.execute(
        select(func.count())
        .select_from(RecipeLike)
        .where(RecipeLike.recipe_id == recipe.id)
    )
    likes = int(cnt_res.scalar_one() or 0)
    # Author username
    try:
        if getattr(recipe, "user", None) and getattr(recipe.user, "username", None):
            author_username = recipe.user.username
        else:
            ures = await db.execute(
                select(User.username).where(User.id == recipe.user_id)
            )
            author_username = ures.scalar_one_or_none()
    except Exception:
        author_username = None
    liked = None
    saved = None
    can_delete = None
    if user is not None:
        liked_res = await db.execute(
            select(func.count())
            .select_from(RecipeLike)
            .where(
                and_(RecipeLike.recipe_id == recipe.id, RecipeLike.user_id == user.id)
            )
        )
        saved_res = await db.execute(
            select(func.count())
            .select_from(SavedRecipe)
            .where(
                and_(SavedRecipe.recipe_id == recipe.id, SavedRecipe.user_id == user.id)
            )
        )
        liked = int(liked_res.scalar_one() or 0) > 0
        saved = int(saved_res.scalar_one() or 0) > 0
        can_delete = getattr(recipe, "user_id", None) == user.id
    # attach
    setattr(recipe, "likes", likes)
    setattr(recipe, "liked", liked)
    setattr(recipe, "saved", saved)
    setattr(recipe, "can_delete", can_delete)
    setattr(recipe, "author_username", author_username)
    return recipe


async def _attach_ingredients(db: AsyncSession, recipe: Recipe):
    try:
        res = await db.execute(
            select(Ingredient.id, Ingredient.name)
            .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(Ingredient.name.asc())
        )
        rows = res.all()
        ings = [IngredientOut(id=r[0], name=r[1]) for r in rows]
    except Exception:
        ings = []
    setattr(recipe, "ingredients", ings)
    return recipe


# Create
async def create_recipe(recipe_data: RecipeCreate, user: User, db: AsyncSession):
    # Exclude non-column fields like 'ingredients' from model init
    payload = recipe_data.model_dump(exclude_unset=True)
    payload.pop("ingredients", None)
    new_recipe = Recipe(**payload, user_id=user.id)
    db.add(new_recipe)
    await db.commit()
    await db.refresh(new_recipe)
    # Attach any provided ingredient_ids if present in payload (future-proof)
    ingredient_ids = getattr(recipe_data, "ingredients", None)
    if isinstance(ingredient_ids, list) and len(ingredient_ids) > 0:
        # Insert unique pairs
        seen = set()
        for iid in ingredient_ids:
            try:
                iid_int = int(iid)
            except Exception:
                continue
            if iid_int in seen:
                continue
            seen.add(iid_int)
            db.add(RecipeIngredient(recipe_id=new_recipe.id, ingredient_id=iid_int))
        await db.commit()
    await _attach_ingredients(db, new_recipe)
    return await _attach_social_fields(db, new_recipe, user)


# Retrieve by id
async def get_recipe_by_id(
    recipe_id: int, db: AsyncSession, user: Optional[User] = None
) -> Optional[Recipe]:
    res = await db.execute(
        select(Recipe).options(joinedload(Recipe.user)).where(Recipe.id == recipe_id)
    )
    recipe = res.scalar_one_or_none()
    if recipe:
        await _attach_social_fields(db, recipe, user)
        await _attach_ingredients(db, recipe)
    return recipe


# List recipes (public)
async def list_recipes(
    db: AsyncSession,
    search: Optional[str] = None,
    user: Optional[User] = None,
    include_self: bool = False,
    ingredient_ids: Optional[list[int]] = None,
) -> Sequence[Recipe]:
    stmt = (
        select(Recipe)
        .options(joinedload(Recipe.user))
        .order_by(Recipe.created_at.desc())
    )
    if search:
        # basic title search
        from sqlalchemy import func as _func

        stmt = stmt.where(_func.lower(Recipe.title).like(f"%{search.lower()}%"))
    # Exclude the current user's own posts in public listing when authenticated unless include_self is True
    if user is not None and getattr(user, "id", None) is not None and not include_self:
        stmt = stmt.where(Recipe.user_id != getattr(user, "id"))
    # Filter by ingredients if provided (ANY of the selected ingredients)
    if ingredient_ids:
        stmt = (
            stmt.join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .where(RecipeIngredient.ingredient_id.in_(ingredient_ids))
            .distinct()
        )
    res = await db.execute(stmt)
    recipes = res.scalars().all()
    # attach social counts and ingredients for listing
    out = []
    for r in recipes:
        await _attach_social_fields(db, r, user)
        await _attach_ingredients(db, r)
        out.append(r)
    return out


# List by user
async def get_recipes_by_user(user: User, db: AsyncSession):
    result = await db.execute(
        select(Recipe)
        .where(Recipe.user_id == user.id)
        .order_by(Recipe.created_at.desc())
    )
    recipes = result.scalars().all()
    out = []
    for r in recipes:
        await _attach_social_fields(db, r, user)
        await _attach_ingredients(db, r)
        out.append(r)
    return out


# Update
async def update_recipe(
    recipe_id: int, data: RecipeUpdate, user: User, db: AsyncSession
) -> Optional[Recipe]:
    recipe = await get_recipe_by_id(recipe_id, db, user)
    if recipe is None or getattr(recipe, "user_id") != user.id:
        return None
    payload = data.model_dump(exclude_unset=True)
    # Extract ingredients if present
    new_ingredient_ids = payload.pop("ingredients", None)
    # Update scalar fields
    for k, v in payload.items():
        setattr(recipe, k, v)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)

    # Replace ingredients if provided
    if new_ingredient_ids is not None:
        try:
            await db.execute(
                delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
            )
            seen = set()
            for iid in new_ingredient_ids or []:
                try:
                    iid_int = int(iid)
                except Exception:
                    continue
                if iid_int in seen:
                    continue
                seen.add(iid_int)
                db.add(RecipeIngredient(recipe_id=recipe.id, ingredient_id=iid_int))
            await db.commit()
        except Exception:
            # best-effort; do not fail the whole update
            await db.rollback()
    await _attach_ingredients(db, recipe)
    return await _attach_social_fields(db, recipe, user)


# Delete
async def delete_recipe(recipe_id: int, user: User, db: AsyncSession) -> bool:
    recipe = await get_recipe_by_id(recipe_id, db, user)
    if recipe is None or getattr(recipe, "user_id") != user.id:
        return False
    await db.delete(recipe)
    await db.commit()
    return True


# Image setter
async def set_recipe_image(
    recipe_id: int, image_url: str, user: User, db: AsyncSession
) -> Optional[Recipe]:
    recipe = await get_recipe_by_id(recipe_id, db, user)
    if recipe is None or getattr(recipe, "user_id") != user.id:
        return None
    setattr(recipe, "image_url", image_url)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)
    await _attach_ingredients(db, recipe)
    return await _attach_social_fields(db, recipe, user)


# Likes
async def add_like(recipe_id: int, user: User, db: AsyncSession) -> int:
    exists = await db.execute(
        select(RecipeLike).where(
            and_(RecipeLike.recipe_id == recipe_id, RecipeLike.user_id == user.id)
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(RecipeLike(recipe_id=recipe_id, user_id=user.id))
        await db.commit()
    cnt = await db.execute(
        select(func.count())
        .select_from(RecipeLike)
        .where(RecipeLike.recipe_id == recipe_id)
    )
    return int(cnt.scalar_one())


async def remove_like(recipe_id: int, user: User, db: AsyncSession) -> int:
    await db.execute(
        delete(RecipeLike).where(
            and_(RecipeLike.recipe_id == recipe_id, RecipeLike.user_id == user.id)
        )
    )
    await db.commit()
    cnt = await db.execute(
        select(func.count())
        .select_from(RecipeLike)
        .where(RecipeLike.recipe_id == recipe_id)
    )
    return int(cnt.scalar_one())


# Saves
async def add_save(recipe_id: int, user: User, db: AsyncSession) -> None:
    exists = await db.execute(
        select(SavedRecipe).where(
            and_(SavedRecipe.recipe_id == recipe_id, SavedRecipe.user_id == user.id)
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(SavedRecipe(recipe_id=recipe_id, user_id=user.id))
        await db.commit()


async def remove_save(recipe_id: int, user: User, db: AsyncSession) -> None:
    await db.execute(
        delete(SavedRecipe).where(
            and_(SavedRecipe.recipe_id == recipe_id, SavedRecipe.user_id == user.id)
        )
    )
    await db.commit()


async def list_saved(user: User, db: AsyncSession):
    res = await db.execute(
        select(Recipe)
        .join(SavedRecipe, SavedRecipe.recipe_id == Recipe.id)
        .where(SavedRecipe.user_id == user.id)
    )
    recipes = res.scalars().all()
    out = []
    for r in recipes:
        await _attach_social_fields(db, r, user)
        await _attach_ingredients(db, r)
        out.append(r)
    return out


# Comments
async def list_comments(recipe_id: int, db: AsyncSession):
    res = await db.execute(
        select(Comment, User.username)
        .join(User, User.id == Comment.user_id)
        .where(Comment.recipe_id == recipe_id)
        .order_by(Comment.created_at.asc())
    )
    items = []
    for c, username in res.all():
        obj = c
        setattr(obj, "username", username)
        items.append(obj)
    return items


async def add_comment(
    recipe_id: int,
    content: str,
    user: User,
    db: AsyncSession,
    parent_id: Optional[int] = None,
):
    comment = Comment(
        recipe_id=recipe_id, user_id=user.id, content=content, parent_id=parent_id
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    setattr(comment, "username", user.username)
    return comment
