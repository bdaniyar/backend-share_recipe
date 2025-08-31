"""
Add bio field to users

Revision ID: 20250811_add_user_bio
Revises: 20250809_add_username_changed_at
Create Date: 2025-08-11
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250811_add_user_bio"
down_revision = "20250809_add_username_changed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bio")
