# filepath: backend/app/db/recipe_ingredients.py
from sqlalchemy import Column, ForeignKey, Index, Integer, UniqueConstraint

from app.db.base import Base


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_ingredient"),
        Index("ix_recipe_ingredients_recipe", "recipe_id"),
        Index("ix_recipe_ingredients_ingredient", "ingredient_id"),
    )
