"""Groups of tasks, for the manage screen.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("task_groups.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "group_id")
    op.drop_table("task_groups")
