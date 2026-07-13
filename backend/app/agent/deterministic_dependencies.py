"""Adaptadores reales del runtime determinista (RF-201/RF-206/RF-208)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.deterministic_pipeline import (
    ExecutionMetadata,
    execute_validated_plan,
    make_soql_executor,
)
from app.agent.deterministic_runtime import (
    DeterministicRuntimeDependencies,
    ExploredColumnValues,
    ProfiledCandidate,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    GroundedSynthesis,
    IntentExtraction,
)
from app.agent.multiquery_retrieval import retrieve_candidates_multiquery
from app.agent.persistence import load_dataset_evidence_metadata
from app.agent.plan_validator import ObservedColumn, ObservedDatasetSchema
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    DatasetOption,
    EligibilityStatus,
    EnumeratedPlanningContext,
    PiiRiskLevel,
)
from app.catalog.search import QueryEmbeddingClient, search_catalog
from app.config import Settings
from app.llm.factory import (
    ainvoke_structured_chat_model,
    get_structured_chat_model,
    usage_from_message,
)
from app.tools.catalog_lookup import fetch_columns_catalog
from app.tools.explorar_valores import explorar_valores


def _secret(value: Any) -> str | None:
    return value.get_secret_value() if value else None


@dataclass
class RuntimeLLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def record(self, *, settings: Settings, raw_message: Any) -> None:
        if raw_message is None:
            return
        item = usage_from_message(settings.llm_provider, settings.llm_model, raw_message)
        self.input_tokens += item.input_tokens
        self.output_tokens += item.output_tokens
        self.estimated_cost_usd = round(
            self.estimated_cost_usd + item.estimated_cost_usd,
            6,
        )


def _model[T: BaseModel](settings: Settings, schema: type[T]) -> Runnable:
    return get_structured_chat_model(
        settings.llm_provider,
        settings.llm_model,
        schema,
        google_api_key=_secret(settings.google_api_key),
        anthropic_api_key=_secret(settings.anthropic_api_key),
        include_raw=True,
        temperature=0,
        timeout=30,
        max_retries=1,
    )


async def _invoke[T: BaseModel](
    model: Runnable,
    schema: type[T],
    messages: list[Any],
    *,
    settings: Settings,
    usage: RuntimeLLMUsage,
) -> T:
    result = await ainvoke_structured_chat_model(model, messages, schema=schema)
    usage.record(settings=settings, raw_message=result.raw_message)
    if not isinstance(result.parsed, schema):
        raise TypeError(f"el proveedor no devolvió {schema.__name__}")
    return result.parsed


def _column_type(value: str) -> ColumnDataType:
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    mapping = {
        "text": ColumnDataType.TEXT,
        "number": ColumnDataType.NUMBER,
        "money": ColumnDataType.NUMBER,
        "double": ColumnDataType.NUMBER,
        "integer": ColumnDataType.INTEGER,
        "checkbox": ColumnDataType.BOOLEAN,
        "boolean": ColumnDataType.BOOLEAN,
        "calendar_date": ColumnDataType.DATE,
        "date": ColumnDataType.DATE,
        "floating_timestamp": ColumnDataType.DATETIME,
        "fixed_timestamp": ColumnDataType.DATETIME,
        "datetime": ColumnDataType.DATETIME,
        "location": ColumnDataType.LOCATION,
        "point": ColumnDataType.LOCATION,
    }
    return mapping.get(normalized, ColumnDataType.UNKNOWN)


def _planning_view(context: EnumeratedPlanningContext) -> dict[str, Any]:
    candidate = context.candidates[0]
    return {
        "dataset_index": candidate.index,
        "title": candidate.title,
        "publisher": candidate.publisher,
        "columns": [
            {
                "column_index": column.index,
                "display_name": column.display_name,
                "data_type": column.data_type.value,
                "pii_risk_level": column.pii_risk_level.value,
            }
            for column in candidate.columns
        ],
    }


def build_real_runtime_dependencies(
    *,
    settings: Settings,
    engine: AsyncEngine,
    http_client: httpx.AsyncClient,
    embedding_client: QueryEmbeddingClient,
    usage: RuntimeLLMUsage,
) -> DeterministicRuntimeDependencies:
    """Construye dependencias productivas sin ninguna ruta de fallback legado."""

    intent_model = _model(settings, IntentExtraction)
    planner_model = _model(settings, EnumeratedPlanSelection)
    synthesis_model = _model(settings, GroundedSynthesis)
    app_token = _secret(settings.socrata_app_token)

    async def extract_intent(question: str) -> IntentExtraction:
        return await _invoke(
            intent_model,
            IntentExtraction,
            [
                SystemMessage(
                    content=(
                        "Extrae la intención analítica. No inventes datasets, columnas, "
                        "identificadores ni consultas. Conserva territorio, entidad y periodo "
                        "solo cuando estén explícitos en la pregunta. `operation` representa "
                        "la agregación necesaria, no la palabra superlativa: preguntas por el "
                        "mayor volumen, la mayor concentración o el total acumulado por grupo "
                        "normalmente requieren SUM; MAX/MIN se reservan para el máximo/mínimo "
                        "de un valor individual; LOOKUP recupera campos de un registro. Conserva "
                        "calificadores sustantivos (por ejemplo tipo, categoría o corte) en "
                        "administrative_terms."
                    )
                ),
                HumanMessage(content=question),
            ],
            settings=settings,
            usage=usage,
        )

    async def retrieve(intent: IntentExtraction):
        async def searcher(query: str, k: int):
            return await search_catalog(
                engine,
                embedding_client=embedding_client,
                query=query,
                k=k,
                stale_after_days=settings.catalog_stale_after_days,
            )

        return await retrieve_candidates_multiquery(intent, searcher=searcher)

    async def profile(dataset_id: str) -> ProfiledCandidate:
        metadata = await load_dataset_evidence_metadata(engine, dataset_id)
        if metadata is None:
            raise LookupError(f"dataset {dataset_id} no existe en catálogo")
        rows = await fetch_columns_catalog(engine, dataset_id)
        if not rows:
            raise LookupError(f"dataset {dataset_id} no tiene columnas observadas")
        ordered_rows = sorted(rows, key=lambda row: row.field_name)
        columns = tuple(
            ColumnOption(
                index=index,
                field_name=row.field_name,
                display_name=row.field_name.replace("_", " "),
                data_type=_column_type(row.data_type),
                pii_risk_level=PiiRiskLevel(row.pii_risk_level),
            )
            for index, row in enumerate(ordered_rows)
        )
        return ProfiledCandidate(
            option=DatasetOption(
                index=0,
                dataset_id=dataset_id,
                title=metadata.name,
                publisher=metadata.publisher or "Publicador no informado",
                columns=columns,
            ),
            schema=ObservedDatasetSchema(
                dataset_id=dataset_id,
                eligibility_status=EligibilityStatus(metadata.eligibility_status),
                pii_risk_level=PiiRiskLevel(metadata.pii_risk_level),
                columns=tuple(
                    ObservedColumn(
                        field_name=column.field_name,
                        data_type=column.data_type,
                        pii_risk_level=column.pii_risk_level,
                    )
                    for column in columns
                ),
            ),
        )

    async def plan(intent, context, explored, validation_error):
        error = (
            {"code": validation_error.code.value, "message": str(validation_error)}
            if validation_error is not None
            else None
        )
        return await _invoke(
            planner_model,
            EnumeratedPlanSelection,
            [
                SystemMessage(
                    content=(
                        "Selecciona exclusivamente índices del contexto. No escribas nombres "
                        "de campos, IDs, SQL o SoQL. COUNT significa count(*). Usa filtros "
                        "tipados y solicita exploración si un valor categórico no está confirmado. "
                        "Si se pregunta qué grupo tiene el mayor o menor agregado, incluye la "
                        "dimensión, la métrica agregada, ordena por esa métrica (DESC o ASC) y usa "
                        "limit=1. No sustituyas SUM por MAX para resolver un ranking. En LOOKUP "
                        "devuelve sólo columnas necesarias para responder. Si una ejecución anual "
                        "tiene registros periódicos, selecciona determinísticamente el registro de "
                        "cierre mediante la columna temporal ordenada DESC y limit=1; aplica los "
                        "calificadores categóricos presentes en la intención."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "intent": intent.model_dump(mode="json"),
                            "context": _planning_view(context),
                            "explored_values": [
                                {
                                    "column_index": item.column_index,
                                    "search_term": item.search_term,
                                    "allowed_values": list(item.values),
                                }
                                for item in explored
                            ],
                            "previous_validation_error": error,
                        },
                        ensure_ascii=False,
                    )
                ),
            ],
            settings=settings,
            usage=usage,
        )

    async def explore(profile, selection, explored):
        explored_indexes = {item.column_index for item in explored}
        target = next(
            (
                item
                for item in selection.filters
                if item.value_type is not None
                and item.value_type.value == "text"
                and item.values
                and item.column_index not in explored_indexes
            ),
            None,
        )
        if target is None:
            raise ValueError("el plan solicitó exploración sin filtro textual pendiente")
        column = profile.option.columns[target.column_index]
        proposed = target.values[0]
        terms = tuple(
            dict.fromkeys(
                (proposed, *(part for part in proposed.split() if len(part) >= 4))
            )
        )[:3]
        output: dict[str, Any] = {"ok": True, "values": ()}
        search_term = proposed
        calls = 0
        for search_term in terms:
            calls += 1
            output = await explorar_valores(
                {
                    "dataset_id": profile.option.dataset_id,
                    "columna": column.field_name,
                    "termino_busqueda": search_term,
                },
                engine=engine,
                http_client=http_client,
                app_token=app_token,
            )
            if output.get("ok") is not True:
                error = output.get("error", {})
                raise ValueError(error.get("message", "falló explorar_valores"))
            if output.get("values"):
                break
        return ExploredColumnValues(
            column_index=target.column_index,
            search_term=search_term,
            values=tuple(str(value) for value in output.get("values", ())),
            tool_calls=calls,
        )

    async def execute(validated):
        metadata = await load_dataset_evidence_metadata(engine, validated.dataset_id)
        if metadata is None:
            raise LookupError(f"dataset {validated.dataset_id} desapareció del catálogo")
        return await execute_validated_plan(
            validated,
            executor=make_soql_executor(
                engine=engine,
                http_client=http_client,
                app_token=app_token,
            ),
            metadata=ExecutionMetadata(
                dataset_name=metadata.name,
                publisher=metadata.publisher,
                dataset_pii_risk_level=metadata.pii_risk_level,
                dataset_eligibility_status=metadata.eligibility_status,
                dataset_eligibility_reasons=metadata.eligibility_reasons,
                data_updated_at=metadata.data_updated_at,
                official_publisher_id=metadata.official_publisher_id,
            ),
        )

    async def synthesize(intent, claims):
        claim_view = [
            {
                "claim_index": index,
                "description": claim.description,
                "display_value": claim.display_value,
                "unit": claim.unit,
            }
            for index, claim in enumerate(claims.claims)
        ]
        return await _invoke(
            synthesis_model,
            GroundedSynthesis,
            [
                SystemMessage(
                    content=(
                        "Redacta una respuesta clara usando solo los claims enumerados. Toda "
                        "respuesta debe citar como máximo 12 claims y priorizar los que contestan "
                        "directamente la pregunta. "
                        "cifra debe copiar un display_value citado. No agregues cálculos, fechas, "
                        "porcentajes ni cantidades que no estén en esos claims."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {"intent": intent.model_dump(mode="json"), "claims": claim_view},
                        ensure_ascii=False,
                    )
                ),
            ],
            settings=settings,
            usage=usage,
        )

    return DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
