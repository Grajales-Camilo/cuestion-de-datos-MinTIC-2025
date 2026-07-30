"""Materialize and index the catalog lexical search vector.

Revision ID: 20260716_0004
Revises: 20260711_0003
Create Date: 2026-07-16 00:00:00

T-614R2: RF-301, RF-302, RF-304, RNF-010.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "20260716_0004"
down_revision: str | None = "20260711_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BUILD_VECTOR_FUNCTION = """
CREATE FUNCTION build_catalog_lexical_search_vector(
    dataset_name text,
    dataset_description text,
    dataset_publisher text,
    dataset_category text,
    dataset_embedding_text text,
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
            dataset_description,
            dataset_publisher,
            dataset_category,
            dataset_embedding_text,
            columns_text
        )
    )
$$
"""

DATASET_TRIGGER_FUNCTION = """
CREATE FUNCTION refresh_catalog_dataset_lexical_search_vector()
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

COLUMNS_TRIGGER_FUNCTION = """
CREATE FUNCTION refresh_catalog_columns_lexical_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
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
        WHERE d.id IN (SELECT DISTINCT dataset_id FROM new_columns);
    ELSIF TG_OP = 'DELETE' THEN
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
        WHERE d.id IN (SELECT DISTINCT dataset_id FROM old_columns);
    ELSE
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
        WHERE d.id IN (
            SELECT dataset_id FROM new_columns
            UNION
            SELECT dataset_id FROM old_columns
        );
    END IF;
    RETURN NULL;
END
$$
"""

BACKFILL = """
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
"""


def upgrade() -> None:
    op.add_column(
        "catalog_datasets",
        sa.Column("lexical_search_vector", TSVECTOR(), nullable=True),
    )
    op.execute(BUILD_VECTOR_FUNCTION)
    op.execute(DATASET_TRIGGER_FUNCTION)
    op.execute(COLUMNS_TRIGGER_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER trg_catalog_datasets_lexical_search_vector
        BEFORE INSERT OR UPDATE OF name, description, publisher, category, embedding_text
        ON catalog_datasets
        FOR EACH ROW
        EXECUTE FUNCTION refresh_catalog_dataset_lexical_search_vector()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_catalog_columns_lexical_search_vector_insert
        AFTER INSERT ON catalog_columns
        REFERENCING NEW TABLE AS new_columns
        FOR EACH STATEMENT
        EXECUTE FUNCTION refresh_catalog_columns_lexical_search_vector()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_catalog_columns_lexical_search_vector_update
        AFTER UPDATE ON catalog_columns
        REFERENCING OLD TABLE AS old_columns NEW TABLE AS new_columns
        FOR EACH STATEMENT
        EXECUTE FUNCTION refresh_catalog_columns_lexical_search_vector()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_catalog_columns_lexical_search_vector_delete
        AFTER DELETE ON catalog_columns
        REFERENCING OLD TABLE AS old_columns
        FOR EACH STATEMENT
        EXECUTE FUNCTION refresh_catalog_columns_lexical_search_vector()
        """
    )
    op.execute(BACKFILL)
    op.alter_column("catalog_datasets", "lexical_search_vector", nullable=False)
    op.create_index(
        "ix_catalog_datasets_lexical_search_vector_gin",
        "catalog_datasets",
        ["lexical_search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_datasets_lexical_search_vector_gin",
        table_name="catalog_datasets",
    )
    op.execute(
        "DROP TRIGGER trg_catalog_columns_lexical_search_vector_delete "
        "ON catalog_columns"
    )
    op.execute(
        "DROP TRIGGER trg_catalog_columns_lexical_search_vector_update "
        "ON catalog_columns"
    )
    op.execute(
        "DROP TRIGGER trg_catalog_columns_lexical_search_vector_insert "
        "ON catalog_columns"
    )
    op.execute(
        "DROP TRIGGER trg_catalog_datasets_lexical_search_vector "
        "ON catalog_datasets"
    )
    op.execute("DROP FUNCTION refresh_catalog_columns_lexical_search_vector()")
    op.execute("DROP FUNCTION refresh_catalog_dataset_lexical_search_vector()")
    op.execute(
        "DROP FUNCTION build_catalog_lexical_search_vector("
        "text, text, text, text, text, text)"
    )
    op.drop_column("catalog_datasets", "lexical_search_vector")
