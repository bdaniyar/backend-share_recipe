# filepath: backend/alembic/versions/20250817_add_recipe_ingredients_table.py
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250817_add_recipe_ing_table"
down_revision = "20250817_add_ingredients_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ingredients",
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "recipe_id", "ingredient_id", name="pk_recipe_ingredients"
        ),
    )
    op.create_unique_constraint(
        "uq_recipe_ingredient", "recipe_ingredients", ["recipe_id", "ingredient_id"]
    )
    op.create_index(
        "ix_recipe_ingredients_recipe",
        "recipe_ingredients",
        ["recipe_id"],
        unique=False,
    )
    op.create_index(
        "ix_recipe_ingredients_ingredient",
        "recipe_ingredients",
        ["ingredient_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recipe_ingredients_ingredient", table_name="recipe_ingredients")
    op.drop_index("ix_recipe_ingredients_recipe", table_name="recipe_ingredients")
    op.drop_constraint("uq_recipe_ingredient", "recipe_ingredients", type_="unique")
    op.drop_table("recipe_ingredients")
