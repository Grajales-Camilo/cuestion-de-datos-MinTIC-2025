"""T2 `perfilar_dataset` (contracts/agent-tools.md §T2, plan.md §9).

Perfilado en vivo antes de consultar: confirma columnas y obtiene valores de
ejemplo reales, para no depender ciegamente de metadatos pobres del portal.
Corre pocas consultas concurrentes (`asyncio.gather`), no una cascada
secuencial (regla del contrato, protege RNF-001).

Pista de corte (`latest_observed_cutoff_hint`): heuristica basada en el
`data_type` de las columnas (`calendar_date`/`date`/`floating_timestamp`) y
en si el nombre sugiere un corte/cierre (mayor confianza) o no (menor
confianza). Es solo una pista para el catalogo -- el corte normativo lo
recalcula T6 sobre cada evidencia (contracts/agent-tools.md §T2).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tools.catalog_lookup import (
    ColumnCatalogRow,
    ColumnProfileUpdate,
    fetch_columns_catalog,
    update_profile_cache,
)
from app.tools.errors import error_envelope, validation_error_envelope
from app.tools.soda_client import SocrataQueryError, SodaClient

MAX_COLUMNS_PER_CALL = 5
DISTINCT_SAMPLE_LIMIT = 15
_CUTOFF_CANDIDATE_DATA_TYPES = {"calendar_date", "date", "floating_timestamp"}
_CUTOFF_PREFERRED_KEYWORDS = ("corte", "final", "cierre", "actualizacion", "fin")
_CUTOFF_CONFIDENCE_PREFERRED = 0.85
_CUTOFF_CONFIDENCE_FALLBACK = 0.6


class PerfilarDatasetInput(BaseModel):
    dataset_id: str = Field(min_length=1)
    columns_of_interest: list[str] = Field(default_factory=list, max_length=MAX_COLUMNS_PER_CALL)


def _pick_cutoff_candidate(columns: list[ColumnCatalogRow]) -> ColumnCatalogRow | None:
    date_columns = [c for c in columns if c.data_type in _CUTOFF_CANDIDATE_DATA_TYPES]
    if not date_columns:
        return None
    for keyword in _CUTOFF_PREFERRED_KEYWORDS:
        for column in date_columns:
            if keyword in column.field_name.lower():
                return column
    return date_columns[0]


def _cutoff_confidence(column: ColumnCatalogRow) -> float:
    name = column.field_name.lower()
    if any(keyword in name for keyword in _CUTOFF_PREFERRED_KEYWORDS):
        return _CUTOFF_CONFIDENCE_PREFERRED
    return _CUTOFF_CONFIDENCE_FALLBACK


async def perfilar_dataset(
    raw_input: dict,
    *,
    engine: AsyncEngine,
    http_client: httpx.AsyncClient,
    app_token: str | None = None,
) -> dict:
    try:
        parsed_input = PerfilarDatasetInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    columns_catalog = await fetch_columns_catalog(engine, parsed_input.dataset_id)
    columns_by_name = {column.field_name: column for column in columns_catalog}
    unknown = [c for c in parsed_input.columns_of_interest if c not in columns_by_name]
    if unknown:
        return error_envelope(
            "SOQL_UNKNOWN_COLUMN",
            f"columnas inexistentes en el dataset: {unknown}",
            valid_columns=sorted(columns_by_name),
        )

    client = SodaClient(http_client, app_token=app_token)
    cutoff_candidate = _pick_cutoff_candidate(columns_catalog)
    columns_of_interest = parsed_input.columns_of_interest

    async def cutoff_query():
        if cutoff_candidate is None:
            return None
        return await client.query(
            parsed_input.dataset_id, select=f"max({cutoff_candidate.field_name}) AS max_value"
        )

    try:
        total_result, *column_results, cutoff_result = await asyncio.gather(
            client.query(parsed_input.dataset_id, select="count(*) AS total"),
            *(
                client.query(
                    parsed_input.dataset_id, select=f"count(*) AS total, count({col}) AS non_null"
                )
                for col in columns_of_interest
            ),
            cutoff_query(),
        )
        distinct_tasks = {
            col: client.query(
                parsed_input.dataset_id, select=col, group=col, limit=DISTINCT_SAMPLE_LIMIT
            )
            for col in columns_of_interest
            if columns_by_name[col].pii_risk_level == "low"
        }
        distinct_values = (
            dict(zip(distinct_tasks, await asyncio.gather(*distinct_tasks.values()), strict=True))
            if distinct_tasks
            else {}
        )
    except SocrataQueryError as exc:
        return error_envelope(exc.code, exc.message)

    total_rows_estimate = _first_int(total_result.rows, "total")

    profile = []
    column_updates = []
    for column, result in zip(columns_of_interest, column_results, strict=True):
        total = _first_int(result.rows, "total")
        non_null = _first_int(result.rows, "non_null")
        null_ratio = round(1 - (non_null / total), 4) if total else 0.0
        distinct_sample: list[object] = []
        if column in distinct_values:
            distinct_sample = [row[column] for row in distinct_values[column].rows if column in row]
        profile.append(
            {
                "field_name": column,
                "data_type": columns_by_name[column].data_type,
                "distinct_sample": distinct_sample,
                "null_ratio": null_ratio,
            }
        )
        column_updates.append(
            ColumnProfileUpdate(
                field_name=column,
                null_ratio=null_ratio,
                sample_values=distinct_sample if column in distinct_values else None,
            )
        )

    cutoff_hint = None
    cutoff_at_iso = None
    if cutoff_candidate is not None and cutoff_result is not None and cutoff_result.rows:
        max_value = cutoff_result.rows[0].get("max_value")
        if max_value:
            cutoff_at_iso = str(max_value)
            cutoff_hint = {
                "latest_observed_cutoff_at": cutoff_at_iso,
                "method": "max_temporal_column",
                "column": cutoff_candidate.field_name,
                "confidence": _cutoff_confidence(cutoff_candidate),
                "inferred_at": datetime.now(UTC).isoformat(),
            }

    if column_updates or cutoff_at_iso is not None:
        await update_profile_cache(engine, parsed_input.dataset_id, column_updates, cutoff_at_iso)

    return {
        "ok": True,
        "dataset_id": parsed_input.dataset_id,
        "total_rows_estimate": total_rows_estimate,
        "latest_observed_cutoff_hint": cutoff_hint,
        "profile": profile,
    }


def _first_int(rows: list[dict], key: str) -> int:
    if not rows:
        return 0
    value = rows[0].get(key)
    return int(value) if value is not None else 0
