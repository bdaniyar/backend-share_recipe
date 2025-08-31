import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250813_add_comment_parent_id"
# Fixed down_revision to actual revision id (was mistakenly filename with suffix)
down_revision = "da981b132c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_comments_parent",
        "comments",
        "comments",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_comments_parent_id", table_name="comments")
    op.drop_constraint("fk_comments_parent", "comments", type_="foreignkey")
    op.drop_column("comments", "parent_id")
