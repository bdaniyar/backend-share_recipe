from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import User
from app.db.session import async_session_maker
from app.utils.security import hash_password


class UserDAO:
    @staticmethod
    async def get_user_by_username(session: AsyncSession, username: str):
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(
        session: AsyncSession, username: str, email: str, password: str
    ):
        hashed_password = hash_password(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_id(cls, user_id: int) -> User | None:
        async with async_session_maker() as session:
            query = select(User).where(User.id == user_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()
