from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db.feedback import Feedback


async def create_feedback(session: AsyncSession, email: str, message: str) -> Feedback:
    feedback = Feedback(email=email, message=message)
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback


async def get_all_feedback(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> List[Feedback]:
    stmt = (
        select(Feedback).order_by(desc(Feedback.created_at)).limit(limit).offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
