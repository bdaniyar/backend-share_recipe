"""add username_changed_at to users

Revision ID: 20250809_add_username_changed_at
Revises: dfc49a560bb4
Create Date: 2025-08-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250809_add_username_changed_at"
down_revision: Union[str, Sequence[str], None] = "dfc49a560bb4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "username_changed_at")
