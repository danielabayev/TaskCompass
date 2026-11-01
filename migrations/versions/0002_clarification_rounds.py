"""Allow more than one clarification round: one note -> a list of notes.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("clarifications", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.execute(
        "UPDATE tasks SET clarifications = jsonb_build_array(clarification_note) "
        "WHERE clarification_note IS NOT NULL"
    )
    op.drop_column("tasks", "clarification_note")


def downgrade() -> None:
    # Keeps the first round only; later rounds are lost on downgrade.
    op.add_column("tasks", sa.Column("clarification_note", sa.Text(), nullable=True))
    op.execute("UPDATE tasks SET clarification_note = clarifications->>0")
    op.drop_column("tasks", "clarifications")
