# filepath: backend/alembic/versions/20250817_add_ingredients_table.py
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250817_add_ingredients_table"
down_revision = "20250813_add_comment_parent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_norm", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_unique_constraint("uq_ingredient_name_norm", "ingredients", ["name_norm"])
    op.create_index(
        "ix_ingredients_name_norm", "ingredients", ["name_norm"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ingredients_name_norm", table_name="ingredients")
    op.drop_constraint("uq_ingredient_name_norm", "ingredients", type_="unique")
    op.drop_table("ingredients")
