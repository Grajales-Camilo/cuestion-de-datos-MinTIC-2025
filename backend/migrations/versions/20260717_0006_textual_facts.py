"""Add isolated persistence for textual facts.

Revision ID: 20260717_0006
Revises: 20260716_0005
Create Date: 2026-07-17 00:00:00

T-615C: RF-703, RF-803, RF-804.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "20260717_0006"
down_revision: str | None = "20260716_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "textual_facts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("source_row_indexes", ARRAY(sa.Integer()), nullable=False),
        sa.Column("columns_used", ARRAY(sa.Text()), nullable=False),
        sa.Column("raw_values", ARRAY(sa.Text()), nullable=False),
        sa.Column("normalized_values", ARRAY(sa.Text()), nullable=False),
        sa.Column("display_value", sa.Text(), nullable=False),
        sa.Column("normalization_profile", sa.Text(), nullable=False),
        sa.Column("operation_params", JSONB(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('direct_text', 'value_presence', 'category_selection', "
            "'argmax_label', 'argmin_label', 'canonical_text_set')",
            name="ck_textual_facts_operation",
        ),
        sa.CheckConstraint(
            "cardinality(source_row_indexes) > 0",
            name="ck_textual_facts_source_rows_nonempty",
        ),
        sa.CheckConstraint(
            "0 <= ALL(source_row_indexes)",
            name="ck_textual_facts_source_rows_nonnegative",
        ),
        sa.CheckConstraint(
            "cardinality(columns_used) > 0",
            name="ck_textual_facts_columns_nonempty",
        ),
        sa.CheckConstraint(
            "cardinality(raw_values) > 0",
            name="ck_textual_facts_raw_values_nonempty",
        ),
        sa.CheckConstraint(
            "cardinality(normalized_values) > 0",
            name="ck_textual_facts_normalized_values_nonempty",
        ),
        sa.CheckConstraint(
            "cardinality(raw_values) = cardinality(normalized_values)",
            name="ck_textual_facts_values_cardinality",
        ),
        sa.CheckConstraint(
            "char_length(fact_text) > 0",
            name="ck_textual_facts_fact_text_nonempty",
        ),
        sa.CheckConstraint(
            "char_length(display_value) > 0",
            name="ck_textual_facts_display_value_nonempty",
        ),
        sa.CheckConstraint(
            "normalization_profile = 'text-es-v1'",
            name="ck_textual_facts_normalization_profile",
        ),
        sa.CheckConstraint(
            "algorithm_version = 'textual-fact-v1'",
            name="ck_textual_facts_algorithm_version",
        ),
        sa.CheckConstraint(
            "source_hash ~ '^sha256-jcs-v1:[0-9a-f]{64}$'",
            name="ck_textual_facts_source_hash",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_results.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_textual_facts_run_id", "textual_facts", ["run_id"])
    op.create_index(
        "ix_textual_facts_evidence_id",
        "textual_facts",
        ["evidence_id"],
    )
    op.create_index(
        "ix_textual_facts_source_hash",
        "textual_facts",
        ["source_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_textual_facts_source_hash", table_name="textual_facts")
    op.drop_index("ix_textual_facts_evidence_id", table_name="textual_facts")
    op.drop_index("ix_textual_facts_run_id", table_name="textual_facts")
    op.drop_table("textual_facts")
