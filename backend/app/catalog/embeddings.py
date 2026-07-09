"""Construccion y persistencia de embeddings del catalogo (T-203, RF-301/RF-304)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.normalize import build_embedding_text
from app.db.models import CatalogColumn, CatalogDataset, CatalogEmbedding

EMBEDDING_DIMENSION = 768
EXPECTED_EMBEDDING_MODEL = "gemini-embedding-2"


class EmbeddingClient(Protocol):
    async def aembed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int = 100,
        task_type: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[list[float]]: ...


@dataclass(frozen=True)
class DatasetEmbeddingInput:
    dataset_id: str
    name: str
    description: str | None
    publisher: str | None
    category: str | None
    column_names: list[str]
    embedding_text: str


@dataclass(frozen=True)
class BuildEmbeddingsSummary:
    active_datasets: int
    selected_datasets: int
    embeddings_upserted: int
    model: str
    dimension: int


def require_supported_embedding_model(model: str | None) -> str:
    if model != EXPECTED_EMBEDDING_MODEL:
        raise ValueError(
            "EMBEDDING_MODEL debe ser gemini-embedding-2 para T-203 "
            "(research.md §1, 768 dimensiones)."
        )
    return model


def ensure_embedding_dimensions(dataset_id: str, embedding: list[float]) -> None:
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding de {dataset_id} tiene dimension {len(embedding)}; "
            f"se esperaba {EMBEDDING_DIMENSION}."
        )


async def _existing_embedding_models(session: AsyncSession) -> set[str]:
    rows = (await session.execute(select(CatalogEmbedding.model).distinct())).scalars().all()
    return set(rows)


async def ensure_model_homogeneity(
    session: AsyncSession,
    *,
    model: str,
    replace_existing_model: bool = False,
) -> None:
    existing_models = await _existing_embedding_models(session)
    conflicting_models = existing_models - {model}
    if not conflicting_models:
        return
    if replace_existing_model:
        await session.execute(delete(CatalogEmbedding))
        return
    formatted = ", ".join(sorted(conflicting_models))
    raise ValueError(
        "catalog_embeddings ya contiene embeddings de otro modelo "
        f"({formatted}). Para no mezclar espacios vectoriales, vacia la tabla "
        "o ejecuta el script con --replace-existing-model."
    )


async def fetch_dataset_embedding_inputs(
    session: AsyncSession,
    *,
    limit: int | None = None,
    only_missing: bool = False,
) -> tuple[int, list[DatasetEmbeddingInput]]:
    active_count = int(
        (
            await session.execute(
                select(func.count()).select_from(CatalogDataset).where(CatalogDataset.api_active)
            )
        ).scalar_one()
    )

    column_names = func.coalesce(
        func.array_remove(
            func.array_agg(aggregate_order_by(CatalogColumn.field_name, CatalogColumn.field_name)),
            None,
        ),
        text("ARRAY[]::text[]"),
    ).label("column_names")

    stmt = (
        select(
            CatalogDataset.id,
            CatalogDataset.name,
            CatalogDataset.description,
            CatalogDataset.publisher,
            CatalogDataset.category,
            column_names,
        )
        .select_from(CatalogDataset)
        .outerjoin(CatalogColumn, CatalogColumn.dataset_id == CatalogDataset.id)
        .where(CatalogDataset.api_active)
        .group_by(CatalogDataset.id)
        .order_by(CatalogDataset.id)
    )
    if only_missing:
        stmt = stmt.outerjoin(CatalogEmbedding, CatalogEmbedding.dataset_id == CatalogDataset.id)
        stmt = stmt.where(CatalogEmbedding.dataset_id.is_(None))
    if limit is not None:
        stmt = stmt.limit(limit)

    inputs: list[DatasetEmbeddingInput] = []
    for row in (await session.execute(stmt)).all():
        columns = list(row.column_names or [])
        text_value = build_embedding_text(
            name=row.name,
            description=row.description,
            publisher_text=row.publisher,
            category=row.category,
            column_names=columns,
        )
        inputs.append(
            DatasetEmbeddingInput(
                dataset_id=row.id,
                name=row.name,
                description=row.description,
                publisher=row.publisher,
                category=row.category,
                column_names=columns,
                embedding_text=text_value,
            )
        )

    return active_count, inputs


async def upsert_embedding_batch(
    session: AsyncSession,
    *,
    batch: list[DatasetEmbeddingInput],
    embeddings: list[list[float]],
    model: str,
) -> int:
    if len(batch) != len(embeddings):
        raise ValueError("La cantidad de embeddings no coincide con la cantidad de datasets.")

    rows = []
    for item, embedding in zip(batch, embeddings, strict=True):
        ensure_embedding_dimensions(item.dataset_id, embedding)
        await session.execute(
            update(CatalogDataset)
            .where(CatalogDataset.id == item.dataset_id)
            .values(embedding_text=item.embedding_text)
        )
        rows.append(
            {
                "dataset_id": item.dataset_id,
                "embedding": embedding,
                "model": model,
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(CatalogEmbedding).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[CatalogEmbedding.dataset_id],
        set_={
            "embedding": stmt.excluded.embedding,
            "model": stmt.excluded.model,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def build_catalog_embeddings(
    engine: AsyncEngine,
    *,
    embedding_client: EmbeddingClient,
    model: str,
    batch_size: int = 100,
    max_retries: int = 3,
    limit: int | None = None,
    only_missing: bool = False,
    replace_existing_model: bool = False,
) -> BuildEmbeddingsSummary:
    model = require_supported_embedding_model(model)
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size debe estar entre 1 y 100.")
    if max_retries < 0:
        raise ValueError("max_retries no puede ser negativo.")
    if limit is not None and limit < 1:
        raise ValueError("limit debe ser mayor que 0.")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await ensure_model_homogeneity(
            session, model=model, replace_existing_model=replace_existing_model
        )
        active_count, inputs = await fetch_dataset_embedding_inputs(
            session, limit=limit, only_missing=only_missing
        )

    upserted = 0
    for start in range(0, len(inputs), batch_size):
        batch = inputs[start : start + batch_size]
        texts = [item.embedding_text for item in batch]
        attempt = 0
        while True:
            try:
                embeddings = await embedding_client.aembed_documents(
                    texts,
                    batch_size=batch_size,
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=EMBEDDING_DIMENSION,
                )
                break
            except Exception:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(2**attempt)
                attempt += 1
        async with session_factory() as session, session.begin():
            await ensure_model_homogeneity(session, model=model)
            upserted += await upsert_embedding_batch(
                session,
                batch=batch,
                embeddings=embeddings,
                model=model,
            )

    return BuildEmbeddingsSummary(
        active_datasets=active_count,
        selected_datasets=len(inputs),
        embeddings_upserted=upserted,
        model=model,
        dimension=EMBEDDING_DIMENSION,
    )
