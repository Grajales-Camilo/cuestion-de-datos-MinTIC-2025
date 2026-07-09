"""Busqueda semantica del catalogo (T-204, RF-302/RF-303/RNF-010)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.catalog.embeddings import (
    EMBEDDING_DIMENSION,
    EXPECTED_EMBEDDING_MODEL,
    ensure_embedding_dimensions,
    require_supported_embedding_model,
)


class QueryEmbeddingClient(Protocol):
    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str | None = None,
        title: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[float]: ...


@dataclass(frozen=True)
class CatalogSearchItem:
    dataset_id: str
    name: str
    publisher: str | None
    official_publisher_id: str | None
    publisher_verification_status: str
    pii_risk_level: str
    eligibility_status: str
    eligibility_reasons: list[object]
    similarity: float
    row_count: int | None
    data_updated_at: datetime | None
    latest_observed_cutoff_at: datetime | None
    metadata_synced_at: datetime
    index_stale: bool
    columns_preview: list[str]


@dataclass(frozen=True)
class CatalogSearchSummary:
    query: str
    results: list[CatalogSearchItem]


SYNONYMS_ES = {
    "escolar": ["educacion", "educativo", "estudiantes", "alumnos", "matricula"],
    "educacion": ["escolar", "educativo", "estudiantes", "alumnos", "matricula"],
}


def normalize_search_query(q: str) -> str:
    query = q.strip()
    if len(query) < 3 or len(query) > 500:
        raise ValueError("q debe tener entre 3 y 500 caracteres despues de trim.")
    return query


def validate_search_k(k: int) -> int:
    if k < 1 or k > 25:
        raise ValueError("k debe estar entre 1 y 25.")
    return k


def build_text_search_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKD", query.casefold())
    ascii_query = "".join(char for char in normalized if not unicodedata.combining(char))
    terms = [term for term in re.findall(r"[a-z0-9]+", ascii_query) if len(term) >= 3]
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        expanded.extend(SYNONYMS_ES.get(term, []))
    unique_terms = list(dict.fromkeys(expanded))
    if not unique_terms:
        return ""
    return " | ".join(f"{term}:*" for term in unique_terms)


async def embed_search_query(
    embedding_client: QueryEmbeddingClient,
    query: str,
) -> list[float]:
    embedding = await embedding_client.aembed_query(
        query,
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=EMBEDDING_DIMENSION,
    )
    ensure_embedding_dimensions("query", embedding)
    return embedding


async def search_catalog(
    engine: AsyncEngine,
    *,
    embedding_client: QueryEmbeddingClient,
    query: str,
    k: int = 10,
    stale_after_days: int = 8,
    model: str = EXPECTED_EMBEDDING_MODEL,
) -> CatalogSearchSummary:
    query = normalize_search_query(query)
    k = validate_search_k(k)
    model = require_supported_embedding_model(model)
    if stale_after_days < 1:
        raise ValueError("stale_after_days debe ser mayor que 0.")

    query_embedding = await embed_search_query(embedding_client, query)
    text_query = build_text_search_query(query)
    stale_threshold = datetime.now(UTC) - timedelta(days=stale_after_days)
    candidate_limit = max(300, k * 20)

    stmt = text(
        """
        WITH vector_candidates AS (
            SELECT
                e.dataset_id,
                e.embedding <=> :query_embedding AS distance
            FROM catalog_embeddings e
            JOIN catalog_datasets d ON d.id = e.dataset_id
            WHERE d.api_active = true
              AND e.model = :model
            ORDER BY e.embedding <=> :query_embedding
            LIMIT :candidate_limit
        )
        SELECT *
        FROM (
        SELECT
            d.id AS dataset_id,
            d.name,
            d.publisher,
            d.official_publisher_id,
            d.publisher_verification_status,
            d.pii_risk_level,
            d.eligibility_status,
            d.eligibility_reasons,
            1 - vc.distance AS similarity,
            d.row_count,
            d.data_updated_at,
            d.latest_observed_cutoff_at,
            d.metadata_synced_at,
            d.metadata_synced_at < :stale_threshold AS index_stale,
            COALESCE(c.columns_preview, ARRAY[]::text[]) AS columns_preview,
            CASE
                WHEN :text_query = '' THEN 0
                ELSE ts_rank_cd(
                    to_tsvector(
                        'spanish',
                        concat_ws(
                            ' ',
                            d.name,
                            d.publisher,
                            d.category,
                            d.description,
                            COALESCE(c.columns_text, '')
                        )
                    ),
                    to_tsquery('spanish', :text_query)
                )
            END AS lexical_rank
        FROM vector_candidates vc
        JOIN catalog_datasets d ON d.id = vc.dataset_id
        LEFT JOIN LATERAL (
            SELECT
                (
                    SELECT array_agg(field_name ORDER BY field_name)
                    FROM (
                        SELECT field_name
                        FROM catalog_columns
                        WHERE dataset_id = d.id
                        ORDER BY field_name
                        LIMIT 5
                    ) column_subset
                ) AS columns_preview,
                (
                    SELECT string_agg(
                        concat_ws(' ', field_name, display_name, description),
                        ' '
                        ORDER BY field_name
                    )
                    FROM catalog_columns
                    WHERE dataset_id = d.id
                ) AS columns_text
        ) c ON true
        ) ranked
        ORDER BY
            similarity + LEAST(0.25, lexical_rank * 0.02) DESC,
            similarity DESC
        LIMIT :k
        """
    ).bindparams(bindparam("query_embedding", type_=Vector(EMBEDDING_DIMENSION)))

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                stmt,
                {
                    "query_embedding": query_embedding,
                    "text_query": text_query,
                    "stale_threshold": stale_threshold,
                    "model": model,
                    "candidate_limit": candidate_limit,
                    "k": k,
                },
            )
        ).all()

    results = [
        CatalogSearchItem(
            dataset_id=row.dataset_id,
            name=row.name,
            publisher=row.publisher,
            official_publisher_id=row.official_publisher_id,
            publisher_verification_status=row.publisher_verification_status,
            pii_risk_level=row.pii_risk_level,
            eligibility_status=row.eligibility_status,
            eligibility_reasons=list(row.eligibility_reasons or []),
            similarity=float(row.similarity),
            row_count=row.row_count,
            data_updated_at=row.data_updated_at,
            latest_observed_cutoff_at=row.latest_observed_cutoff_at,
            metadata_synced_at=row.metadata_synced_at,
            index_stale=bool(row.index_stale),
            columns_preview=list(row.columns_preview or []),
        )
        for row in rows
    ]
    return CatalogSearchSummary(query=query, results=results)
