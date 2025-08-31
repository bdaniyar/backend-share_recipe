# db/recipe.py
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    instructions = Column(Text)
    image_url = Column(String, nullable=True)
    is_published = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="recipes")
    # Optional category link (table can be added later). Keep as plain Integer to avoid FK errors until categories exist.
    category_id = Column(Integer, nullable=True)
