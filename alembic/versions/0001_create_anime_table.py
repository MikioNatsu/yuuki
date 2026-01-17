"""create anime table

Revision ID: 6b4d2b3c3a12
Revises:
Create Date: 2026-01-17 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6b4d2b3c3a12"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "anime",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_title", sa.String(length=256), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=True),
        sa.Column("platform_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "(official_url IS NOT NULL) OR (platform_url IS NOT NULL)",
            name="ck_anime_has_at_least_one_url",
        ),
    )
    op.create_index("ix_anime_canonical_title", "anime", ["canonical_title"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_anime_canonical_title", table_name="anime")
    op.drop_table("anime")
