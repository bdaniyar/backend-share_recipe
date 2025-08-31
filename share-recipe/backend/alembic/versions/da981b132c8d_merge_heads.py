"""merge heads

Revision ID: da981b132c8d
Revises: 20250811_add_user_bio, 4e4a9eac02df
Create Date: 2025-08-11 20:44:58.892181

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "da981b132c8d"
down_revision: Union[str, Sequence[str], None] = (
    "20250811_add_user_bio",
    "4e4a9eac02df",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
