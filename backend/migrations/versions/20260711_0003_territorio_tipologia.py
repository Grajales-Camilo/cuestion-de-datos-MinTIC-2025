"""Add territorio_tipologia table.

Revision ID: 20260711_0003
Revises: 20260709_0002
Create Date: 2026-07-11 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0003"
down_revision: str | None = "20260709_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "territorio_tipologia",
        sa.Column("divipola_code", sa.Text(), primary_key=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("tipologia_dnp", sa.Text(), nullable=False),
        sa.Column("categoria_ley_617", sa.Text()),
        sa.Column("poblacion", sa.BigInteger()),
        sa.Column("ingresos_totales_cop", sa.Numeric()),
        sa.Column("vigencia", sa.Integer(), nullable=False),
        sa.Column("fuente_archivo", sa.Text(), nullable=False),
        sa.Column(
            "cargado_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["divipola_code"], ["divipola_entries.code"]),
        sa.CheckConstraint(
            "level IN ('department', 'municipality')",
            name="ck_territorio_tipologia_level",
        ),
    )


def downgrade() -> None:
    op.drop_table("territorio_tipologia")
