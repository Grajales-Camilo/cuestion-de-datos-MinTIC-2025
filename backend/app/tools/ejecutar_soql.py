"""T5 `ejecutar_soql` (contracts/agent-tools.md §T5, RF-207).

Unica herramienta que trae datos masivos. Ejecuta contra la SODA API solo
despues de pasar la guardia estructural de `app/tools/soql_parser.py`
(gramatica restringida + catalogo); nunca llama a Socrata si la guardia
rechaza la consulta.

`rows` devuelve las filas completas (hasta el `LIMIT` canonico, maximo 1000
por RF-201) -- son las que persiste T6/Evidencia. `llm_view.rows_shown` es
metadato para quien construya el mensaje hacia el LLM (T-303): al contexto
del modelo solo deben entrar <= 50 filas; esta funcion no trunca `rows` por
si misma porque el consumidor todavia necesita el conjunto completo para
construir la Evidencia.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tools.catalog_lookup import fetch_dataset_catalog_info
from app.tools.errors import error_envelope, validation_error_envelope
from app.tools.soda_client import SocrataQueryError, SodaClient
from app.tools.soql_parser import SoqlGuardError, validate_and_canonicalize

LLM_VIEW_MAX_ROWS = 50


class EjecutarSoqlInput(BaseModel):
    dataset_id: str = Field(min_length=1)
    soql: str = Field(min_length=1, max_length=5000)
    purpose: str = Field(min_length=1, max_length=500)


async def ejecutar_soql(
    raw_input: dict,
    *,
    engine: AsyncEngine,
    http_client: httpx.AsyncClient,
    app_token: str | None = None,
) -> dict:
    try:
        parsed_input = EjecutarSoqlInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    dataset_info = await fetch_dataset_catalog_info(engine, parsed_input.dataset_id)
    if dataset_info is None:
        return error_envelope(
            "DATASET_INACTIVE", f"el dataset {parsed_input.dataset_id!r} no existe en el catalogo"
        )

    try:
        canonical = validate_and_canonicalize(parsed_input.soql, dataset_info)
    except SoqlGuardError as exc:
        extra = {} if exc.valid_columns is None else {"valid_columns": exc.valid_columns}
        return error_envelope(exc.code, exc.message, **extra)

    client = SodaClient(http_client, app_token=app_token)
    try:
        result = await client.query(
            parsed_input.dataset_id,
            select=canonical.select_clause,
            where=canonical.where_clause,
            group=canonical.group_by_clause,
            having=canonical.having_clause,
            order=canonical.order_by_clause,
            limit=canonical.limit,
            offset=canonical.offset,
        )
    except SocrataQueryError as exc:
        return error_envelope(exc.code, exc.message)

    row_count = len(result.rows)
    return {
        "ok": True,
        "canonical_soql": canonical.canonical_soql,
        "rows": result.rows,
        "row_count": row_count,
        "executed_at": result.executed_at.isoformat(),
        "source_url": result.source_url,
        "llm_view": {
            "rows_shown": min(LLM_VIEW_MAX_ROWS, row_count),
            "note": "al contexto del LLM entran max. 50 filas; el resto viaja directo a la "
            "Evidencia",
        },
    }
