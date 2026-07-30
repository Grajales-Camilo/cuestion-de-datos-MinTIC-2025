"""Busqueda semantica del catalogo (T-204, RF-302/RF-303/RNF-010)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
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
    columns_all: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CatalogSearchSummary:
    query: str
    results: list[CatalogSearchItem]


# Lista pequeña y curada a mano, NO un tesauro general. Existe porque el
# stemmer 'spanish' de PostgreSQL solo normaliza variantes morfologicas de
# una misma raiz (escolar/escolares), no relaciona raices distintas
# (escolar <-> educacion) -- y la busqueda vectorial por si sola tampoco
# alcanzaba: los datasets reales del MEN sobre desercion escolar quedaban
# con similitud coseno ~0.60-0.63 (fuera del top-25) contra ~0.68-0.70 de
# datasets menos relevantes (verificado T-204 con el indice real, 8.416
# embeddings). Este boost lexical (ver `lexical_rank` mas abajo) es un
# parche deliberadamente acotado para ese hueco puntual, no una solucion
# general de sinonimos en espanol.
#
# Limite conocido: solo cubre los pares agregados aqui a mano; una consulta
# con un sinonimo no listado simplemente no se beneficia del boost (no
# rompe nada, ver test_build_text_search_query_returns_plain_terms_when_
# no_synonym_matches). Si aparecen mas huecos reales (via golden queries de
# research.md o quejas de uso real), amplia esta lista con evidencia
# concreta -- no adivines pares "razonables". Una solucion mas de fondo
# (tesauro de PostgreSQL via `CREATE TEXT SEARCH DICTIONARY ... synonym`,
# alimentado por un fixture versionado como `official_publishers.json`)
# queda fuera de alcance de este parche; considerala si esta lista crece
# mucho o si el problema se repite con otros pares no relacionados.
SYNONYMS_ES: dict[str, list[str]] = {
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
        ),
        lexical_candidates AS (
            SELECT d.id AS dataset_id
            FROM catalog_datasets d
            WHERE d.api_active = true
              AND :text_query <> ''
              AND d.lexical_search_vector @@ to_tsquery('spanish', :text_query)
            ORDER BY ts_rank_cd(
                d.lexical_search_vector,
                to_tsquery('spanish', :text_query)
            ) DESC
            LIMIT 100
        ),
        candidate_ids AS (
            SELECT dataset_id FROM vector_candidates
            UNION
            SELECT dataset_id FROM lexical_candidates
        ),
        ranked AS (
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
            CASE
                WHEN :text_query = '' THEN 0
                ELSE ts_rank_cd(
                    d.lexical_rank_vector,
                    to_tsquery('spanish', :text_query)
                )
            END AS lexical_rank
        FROM candidate_ids candidates
        JOIN catalog_datasets d ON d.id = candidates.dataset_id
        JOIN catalog_embeddings e ON e.dataset_id = d.id AND e.model = :model
        CROSS JOIN LATERAL (
            SELECT e.embedding <=> :query_embedding AS distance
        ) vc
        ),
        ranked_top AS (
            SELECT *
            FROM ranked
            ORDER BY
                similarity + LEAST(0.25, lexical_rank * 0.02) DESC,
                similarity DESC
            LIMIT :k
        )
        SELECT
            ranked_top.*,
            COALESCE(c.columns_preview, ARRAY[]::text[]) AS columns_preview,
            COALESCE(c.columns_all, ARRAY[]::text[]) AS columns_all
        FROM ranked_top
        LEFT JOIN LATERAL (
            SELECT
                (
                    SELECT array_agg(field_name ORDER BY field_name)
                    FROM (
                        SELECT field_name
                        FROM catalog_columns
                        WHERE dataset_id = ranked_top.dataset_id
                        ORDER BY field_name
                        LIMIT 5
                    ) column_subset
                ) AS columns_preview,
                (
                    SELECT array_agg(field_name ORDER BY field_name)
                    FROM catalog_columns
                    WHERE dataset_id = ranked_top.dataset_id
                ) AS columns_all
        ) c ON true
        ORDER BY
            similarity + LEAST(0.25, lexical_rank * 0.02) DESC,
            similarity DESC
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
            columns_all=list(row.columns_all or []),
        )
        for row in rows
    ]
    return CatalogSearchSummary(query=query, results=results)
