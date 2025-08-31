# filepath: backend/app/db/ingredients.py
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.db.base import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    # Original display name (case-preserving)
    name = Column(String(100), nullable=False)
    # Normalized name for uniqueness (lowercase + trim)
    name_norm = Column(String(120), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("name_norm", name="uq_ingredient_name_norm"),)
