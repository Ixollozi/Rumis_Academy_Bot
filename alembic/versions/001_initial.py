"""Initial schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("lang", sa.String(8), server_default="ru"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"], unique=True)

    op.create_table(
        "exam_dates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_day", sa.Date(), nullable=False),
        sa.Column("seat_limit", sa.Integer(), server_default="10"),
        sa.Column("is_closed", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("exam_day", name="uq_exam_day"),
    )
    op.create_index("ix_exam_dates_exam_day", "exam_dates", ["exam_day"])

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("price_own", sa.Integer(), server_default="75000"),
        sa.Column("price_new", sa.Integer(), server_default="150000"),
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "exam_date_id",
            sa.Integer(),
            sa.ForeignKey("exam_dates.id", ondelete="CASCADE"),
        ),
        sa.Column("full_name_en", sa.String(200), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("post_exam_sent", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_bookings_status", "bookings", ["status"])


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("app_settings")
    op.drop_table("exam_dates")
    op.drop_table("users")
