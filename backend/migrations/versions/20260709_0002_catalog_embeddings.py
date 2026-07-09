"""Add catalog embeddings table.

Revision ID: 20260709_0002
Revises: 20260708_0001
Create Date: 2026-07-09 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260709_0002"
down_revision: str | None = "20260708_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_embeddings",
        sa.Column("dataset_id", sa.Text(), primary_key=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["catalog_datasets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_catalog_embeddings_embedding_hnsw",
        "catalog_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_embeddings_embedding_hnsw", table_name="catalog_embeddings")
    op.drop_table("catalog_embeddings")
