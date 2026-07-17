"""Materialize the exact lexical ranking vector.

Revision ID: 20260716_0005
Revises: 20260716_0004
Create Date: 2026-07-16 00:00:01

T-614R2: RF-301, RF-302, RF-304, RNF-010.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "20260716_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RANK_FUNCTION = """
CREATE FUNCTION build_catalog_lexical_rank_vector(
    dataset_name text,
    dataset_publisher text,
    dataset_category text,
    dataset_description text,
    columns_text text
) RETURNS tsvector
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT to_tsvector(
        'spanish',
        concat_ws(
            ' ',
            dataset_name,
            dataset_publisher,
            dataset_category,
            dataset_description,
            columns_text
        )
    )
$$
"""

DATASET_TRIGGER_WITH_RANK = """
CREATE OR REPLACE FUNCTION refresh_catalog_dataset_lexical_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    aggregated_columns text;
BEGIN
    SELECT COALESCE(
        string_agg(
            concat_ws(' ', c.field_name, c.display_name, c.description),
            ' ' ORDER BY c.field_name
        ),
        ''
    )
    INTO aggregated_columns
    FROM catalog_columns c
    WHERE c.dataset_id = NEW.id;

    NEW.lexical_search_vector := build_catalog_lexical_search_vector(
        NEW.name,
        NEW.description,
        NEW.publisher,
        NEW.category,
        NEW.embedding_text,
        aggregated_columns
    );
    NEW.lexical_rank_vector := build_catalog_lexical_rank_vector(
        NEW.name,
        NEW.publisher,
        NEW.category,
        NEW.description,
        aggregated_columns
    );
    RETURN NEW;
END
$$
"""

COLUMNS_TRIGGER_WITH_RANK = """
CREATE OR REPLACE FUNCTION refresh_catalog_columns_lexical_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_ids text[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT array_agg(DISTINCT dataset_id) INTO affected_ids FROM new_columns;
    ELSIF TG_OP = 'DELETE' THEN
        SELECT array_agg(DISTINCT dataset_id) INTO affected_ids FROM old_columns;
    ELSE
        SELECT array_agg(DISTINCT dataset_id)
        INTO affected_ids
        FROM (
            SELECT dataset_id FROM new_columns
            UNION
            SELECT dataset_id FROM old_columns
        ) changed;
    END IF;

    UPDATE catalog_datasets d
    SET
        lexical_search_vector = build_catalog_lexical_search_vector(
            d.name,
            d.description,
            d.publisher,
            d.category,
            d.embedding_text,
            COALESCE(
                (
                    SELECT string_agg(
                        concat_ws(' ', c.field_name, c.display_name, c.description),
                        ' ' ORDER BY c.field_name
                    )
                    FROM catalog_columns c
                    WHERE c.dataset_id = d.id
                ),
                ''
            )
        ),
        lexical_rank_vector = build_catalog_lexical_rank_vector(
            d.name,
            d.publisher,
            d.category,
            d.description,
            COALESCE(
                (
                    SELECT string_agg(
                        concat_ws(' ', c.field_name, c.display_name, c.description),
                        ' ' ORDER BY c.field_name
                    )
                    FROM catalog_columns c
                    WHERE c.dataset_id = d.id
                ),
                ''
            )
        )
    WHERE d.id = ANY(affected_ids);
    RETURN NULL;
END
$$
"""

DATASET_TRIGGER_SEARCH_ONLY = """
CREATE OR REPLACE FUNCTION refresh_catalog_dataset_lexical_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.lexical_search_vector := build_catalog_lexical_search_vector(
        NEW.name,
        NEW.description,
        NEW.publisher,
        NEW.category,
        NEW.embedding_text,
        COALESCE(
            (
                SELECT string_agg(
                    concat_ws(' ', c.field_name, c.display_name, c.description),
                    ' ' ORDER BY c.field_name
                )
                FROM catalog_columns c
                WHERE c.dataset_id = NEW.id
            ),
            ''
        )
    );
    RETURN NEW;
END
$$
"""

COLUMNS_TRIGGER_SEARCH_ONLY = """
CREATE OR REPLACE FUNCTION refresh_catalog_columns_lexical_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_ids text[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT array_agg(DISTINCT dataset_id) INTO affected_ids FROM new_columns;
    ELSIF TG_OP = 'DELETE' THEN
        SELECT array_agg(DISTINCT dataset_id) INTO affected_ids FROM old_columns;
    ELSE
        SELECT array_agg(DISTINCT dataset_id)
        INTO affected_ids
        FROM (
            SELECT dataset_id FROM new_columns
            UNION
            SELECT dataset_id FROM old_columns
        ) changed;
    END IF;

    UPDATE catalog_datasets d
    SET lexical_search_vector = build_catalog_lexical_search_vector(
        d.name,
        d.description,
        d.publisher,
        d.category,
        d.embedding_text,
        COALESCE(
            (
                SELECT string_agg(
                    concat_ws(' ', c.field_name, c.display_name, c.description),
                    ' ' ORDER BY c.field_name
                )
                FROM catalog_columns c
                WHERE c.dataset_id = d.id
            ),
            ''
        )
    )
    WHERE d.id = ANY(affected_ids);
    RETURN NULL;
END
$$
"""

BACKFILL = """
UPDATE catalog_datasets d
SET lexical_rank_vector = build_catalog_lexical_rank_vector(
    d.name,
    d.publisher,
    d.category,
    d.description,
    COALESCE(
        (
            SELECT string_agg(
                concat_ws(' ', c.field_name, c.display_name, c.description),
                ' ' ORDER BY c.field_name
            )
            FROM catalog_columns c
            WHERE c.dataset_id = d.id
        ),
        ''
    )
)
"""


def upgrade() -> None:
    op.add_column(
        "catalog_datasets",
        sa.Column("lexical_rank_vector", TSVECTOR(), nullable=True),
    )
    op.execute(RANK_FUNCTION)
    op.execute(DATASET_TRIGGER_WITH_RANK)
    op.execute(COLUMNS_TRIGGER_WITH_RANK)
    op.execute(BACKFILL)
    op.alter_column("catalog_datasets", "lexical_rank_vector", nullable=False)


def downgrade() -> None:
    op.execute(DATASET_TRIGGER_SEARCH_ONLY)
    op.execute(COLUMNS_TRIGGER_SEARCH_ONLY)
    op.drop_column("catalog_datasets", "lexical_rank_vector")
    op.execute(
        "DROP FUNCTION build_catalog_lexical_rank_vector("
        "text, text, text, text, text)"
    )
