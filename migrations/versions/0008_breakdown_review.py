"""Review of the breakdown after the task ends.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("breakdown_review", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "breakdown_review")
