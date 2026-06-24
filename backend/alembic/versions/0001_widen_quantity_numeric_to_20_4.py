"""widen quantity numeric to 20_4

Revision ID: 0001
Revises:
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "consumption_records", "quantity",
        type_=sa.Numeric(20, 4), existing_nullable=False,
    )
    op.alter_column(
        "closing_stocks", "quantity",
        type_=sa.Numeric(20, 4), existing_nullable=False,
    )
    op.alter_column(
        "open_indents", "quantity",
        type_=sa.Numeric(20, 4), existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "open_indents", "quantity",
        type_=sa.Numeric(12, 4), existing_nullable=False,
    )
    op.alter_column(
        "closing_stocks", "quantity",
        type_=sa.Numeric(12, 4), existing_nullable=False,
    )
    op.alter_column(
        "consumption_records", "quantity",
        type_=sa.Numeric(12, 4), existing_nullable=False,
    )
