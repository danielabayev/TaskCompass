"""Breakdown into editable subtasks before the (whole-task) time estimate.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("breakdown", postgresql.JSONB(), nullable=True))
    op.add_column("tasks", sa.Column("breakdown_confirmed", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("tasks", "breakdown_confirmed")
    op.drop_column("tasks", "breakdown")
