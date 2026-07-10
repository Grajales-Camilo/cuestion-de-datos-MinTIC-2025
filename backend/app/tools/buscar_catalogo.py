"""T1 `buscar_catalogo` (contracts/agent-tools.md §T1, RF-203/302).

Envuelve `app.catalog.search.search_catalog` (T-204) y la enriquece con la
lista completa de columnas por dataset (el agente la necesita para planear
SoQL, a diferencia de `/v2/catalog/search` que solo expone un preview de 5
columnas para la UI publica) y con la descripcion truncada a 300 caracteres.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.catalog.search import QueryEmbeddingClient, search_catalog
from app.tools.errors import error_envelope, validation_error_envelope

DESCRIPTION_SNIPPET_MAX_CHARS = 300


class BuscarCatalogoInput(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    k: int = Field(default=8, ge=1, le=10)


async def _fetch_descriptions_and_columns(
    engine: AsyncEngine, dataset_ids: list[str]
) -> dict[str, dict]:
    if not dataset_ids:
        return {}
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT
                        d.id AS dataset_id,
                        d.description,
                        COALESCE(
                            json_agg(
                                json_build_object(
                                    'field_name', c.field_name,
                                    'data_type', c.data_type,
                                    'description', c.description
                                ) ORDER BY c.field_name
                            ) FILTER (WHERE c.field_name IS NOT NULL),
                            '[]'
                        ) AS columns
                    FROM catalog_datasets d
                    LEFT JOIN catalog_columns c ON c.dataset_id = d.id
                    WHERE d.id = ANY(:ids)
                    GROUP BY d.id, d.description
                    """
                ),
                {"ids": dataset_ids},
            )
        ).all()
    return {
        row.dataset_id: {"description": row.description, "columns": row.columns} for row in rows
    }


def _truncate_description(description: str | None) -> str:
    if not description:
        return ""
    if len(description) <= DESCRIPTION_SNIPPET_MAX_CHARS:
        return description
    return description[:DESCRIPTION_SNIPPET_MAX_CHARS]


async def buscar_catalogo(
    raw_input: dict,
    *,
    engine: AsyncEngine,
    embedding_client: QueryEmbeddingClient,
) -> dict:
    try:
        parsed_input = BuscarCatalogoInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    try:
        summary = await search_catalog(
            engine, embedding_client=embedding_client, query=parsed_input.query, k=parsed_input.k
        )
    except ValueError as exc:
        return error_envelope("INVALID_INPUT", str(exc))

    dataset_ids = [item.dataset_id for item in summary.results]
    extra_by_dataset = await _fetch_descriptions_and_columns(engine, dataset_ids)

    results = []
    for item in summary.results:
        extra = extra_by_dataset.get(item.dataset_id, {"description": None, "columns": []})
        results.append(
            {
                "dataset_id": item.dataset_id,
                "name": item.name,
                "publisher": item.publisher,
                "official_publisher_id": item.official_publisher_id,
                "publisher_verification_status": item.publisher_verification_status,
                "description_snippet": _truncate_description(extra["description"]),
                "similarity": item.similarity,
                "row_count": item.row_count,
                "data_updated_at": item.data_updated_at,
                "latest_observed_cutoff_at": item.latest_observed_cutoff_at,
                "pii_risk_level": item.pii_risk_level,
                "eligibility_status": item.eligibility_status,
                "eligibility_reasons": item.eligibility_reasons,
                "columns": extra["columns"],
            }
        )

    return {"ok": True, "results": results}
