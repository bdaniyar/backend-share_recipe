# filepath: backend/app/db/dao/ingredients.py
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ingredients import Ingredient


def _normalize(name: str) -> str:
    return " ".join(
        name.strip().lower().split()
    )  # trim + collapse whitespace + lowercase


async def search_ingredients(
    session: AsyncSession, q: str, limit: int = 20
) -> List[Ingredient]:
    nq = _normalize(q)
    stmt = (
        select(Ingredient)
        .where(Ingredient.name_norm.like(f"%{nq}%"))
        .order_by(Ingredient.name.asc())
        .limit(limit)
    )
    try:
        res = await session.execute(stmt)
        return res.scalars().all()
    except ProgrammingError:
        # Table likely not migrated yet; fail closed with empty list
        return []
    except Exception:
        # Be defensive on cold starts
        return []


async def get_by_normalized(
    session: AsyncSession, normalized: str
) -> Optional[Ingredient]:
    stmt = select(Ingredient).where(Ingredient.name_norm == normalized)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def create_ingredient(session: AsyncSession, name: str) -> Ingredient:
    ing = Ingredient(name=name, name_norm=_normalize(name))
    session.add(ing)
    await session.commit()
    await session.refresh(ing)
    return ing
