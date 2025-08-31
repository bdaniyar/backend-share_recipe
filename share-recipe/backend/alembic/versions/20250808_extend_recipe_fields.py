import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250808_extend_recipe_fields"
down_revision = "03feb1054790"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("image_url", sa.String(), nullable=True))
    op.add_column(
        "recipes",
        sa.Column(
            "is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )
    # Always add category_id column; add FK only if categories table exists
    op.add_column("recipes", sa.Column("category_id", sa.Integer(), nullable=True))
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "categories" in inspector.get_table_names():
        op.create_foreign_key(
            "fk_recipes_category", "recipes", "categories", ["category_id"], ["id"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "recipes" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("recipes")]
        if "fk_recipes_category" in [
            c.get("name") for c in inspector.get_foreign_keys("recipes")
        ]:
            op.drop_constraint("fk_recipes_category", "recipes", type_="foreignkey")
        if "category_id" in cols:
            op.drop_column("recipes", "category_id")
        if "is_published" in cols:
            op.drop_column("recipes", "is_published")
        if "image_url" in cols:
            op.drop_column("recipes", "image_url")
