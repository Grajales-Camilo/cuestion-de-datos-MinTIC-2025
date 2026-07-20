"""Adaptadores reales del runtime determinista (RF-201/RF-206/RF-208)."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
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
    DeterministicToolInfrastructureError,
    ExploredColumnValues,
    ProfiledCandidate,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    GroundedSynthesis,
    IntentExtraction,
    QuantitativePlanSelection,
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
from app.quality.claim_labels import claim_is_relevant_to_narrative, intent_relevance_tokens
from app.quality.grounded_facts import GroundedSynthesisPlan
from app.quality.grounded_synthesis import AllowedGroundedFacts, AllowedQuantitativeFact
from app.tools.catalog_lookup import fetch_columns_catalog
from app.tools.explorar_valores import explorar_valores


def _secret(value: Any) -> str | None:
    return value.get_secret_value() if value else None


def _exploration_terms(proposed: str, max_tool_calls: int) -> tuple[str, ...]:
    """Prioriza frase y tokens originales antes de variantes sin tildes."""

    original_tokens = tuple(
        token for token in re.findall(r"[^\W_]+", proposed, flags=re.UNICODE) if len(token) >= 4
    )
    plain = "".join(
        character
        for character in unicodedata.normalize("NFKD", proposed)
        if not unicodedata.combining(character)
    )
    plain_tokens = tuple(token for token in re.findall(r"[A-Za-z0-9]+", plain) if len(token) >= 4)
    candidates = (proposed, *original_tokens, plain, *plain_tokens)
    return tuple(dict.fromkeys(term for term in candidates if term))[:max_tool_calls]


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


# T-617B0-R4/R4A: presupuesto de razonamiento del planificador Gemini
# (diagnóstico `backend/eval/reports/t617b-d1-pilot005-timeout-diagnosis.md`
# §8/§9: la prueba mínima de disponibilidad del modelo, sin thinking_budget y
# sin el payload real de build_plan, respondió en ~1.4 s; build_plan real de
# `pilot-005-empleo-publico` agotó los dos intentos de 30 s con 504 en las
# tres corridas observadas; con thinking_budget=1024 build_plan respondió en
# ~5.2 s pero con salida estructurada inválida; con thinking_budget=4096
# build_plan respondió en ~2.9 s con salida estructurada válida). Constante
# única, sin excepción por `case_id`/`dataset_id`/pregunta: se aplica a TODAS
# las invocaciones del planificador, para todos los casos golden.
PLANNER_THINKING_BUDGET_TOKENS = 4096

# T-617B0-R4A: la evidencia de §8/§9 del diagnóstico se produjo
# específicamente contra `gemini-2.5-flash`; no hay evidencia equivalente
# para otro modelo Google. El presupuesto de razonamiento se acota a este
# modelo exacto -- cualquier otro modelo Google (presente o futuro) queda
# sin `thinking_budget`, igual que Anthropic.
_PLANNER_THINKING_BUDGET_LLM_MODEL = "gemini-2.5-flash"


def _model[T: BaseModel](
    settings: Settings,
    schema: type[T],
    *,
    thinking_budget: int | None = None,
) -> Runnable:
    """Construye el modelo estructurado (RF-206).

    ``thinking_budget`` es específico de ``ChatGoogleGenerativeAI``
    (``langchain_google_genai._common.thinking_budget``, en tokens): NUNCA se
    envía cuando ``settings.llm_provider != "google"`` (Anthropic no expone
    este parámetro) ni cuando ``settings.llm_model !=
    "gemini-2.5-flash"`` (T-617B0-R4A: sin evidencia para otro modelo Google).
    No modifica ``timeout``/``max_retries``, que se mantienen fijos en 30/2
    para todos los modelos y proveedores."""

    provider_kwargs: dict[str, Any] = {}
    if (
        thinking_budget is not None
        and settings.llm_provider == "google"
        and settings.llm_model == _PLANNER_THINKING_BUDGET_LLM_MODEL
    ):
        provider_kwargs["thinking_budget"] = thinking_budget
    return get_structured_chat_model(
        settings.llm_provider,
        settings.llm_model,
        schema,
        google_api_key=_secret(settings.google_api_key),
        anthropic_api_key=_secret(settings.anthropic_api_key),
        include_raw=True,
        temperature=0,
        timeout=30,
        max_retries=2,
        **provider_kwargs,
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
    is_cancelled: Callable[[], bool] | None = None,
) -> DeterministicRuntimeDependencies:
    """Construye dependencias productivas sin ninguna ruta de fallback legado."""

    intent_model = _model(settings, IntentExtraction)
    planner_schema = (
        EnumeratedPlanSelection
        if settings.deterministic_textual_facts_enabled
        else QuantitativePlanSelection
    )
    # T-617B0-R4/R4A: solo el planificador recibe thinking_budget, y solo se
    # aplica de verdad cuando el modelo efectivo es gemini-2.5-flash (ver
    # _model); intent, síntesis y plan de síntesis quedan sin cambios.
    planner_model = _model(settings, planner_schema, thinking_budget=PLANNER_THINKING_BUDGET_TOKENS)
    synthesis_model = _model(settings, GroundedSynthesis)
    synthesis_plan_model = (
        _model(settings, GroundedSynthesisPlan)
        if settings.deterministic_textual_facts_enabled
        else None
    )
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
                        "de un valor individual; LOOKUP recupera campos de un registro. Los "
                        "estados "
                        "presupuestales acumulados por mes son snapshots: una pregunta por la "
                        "ejecución o el pago anual requiere LOOKUP del corte de cierre, no SUM "
                        "entre "
                        "meses. Conserva "
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
                display_name=row.display_name or row.field_name.replace("_", " "),
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
        selection = await _invoke(
            planner_model,
            planner_schema,
            [
                SystemMessage(
                    content=(
                        "Selecciona exclusivamente índices del contexto. No escribas nombres "
                        "de campos, IDs, SQL o SoQL. COUNT significa count(*). Usa filtros "
                        "tipados y solicita exploración si un valor categórico no está confirmado. "
                        "Si se pregunta qué grupo tiene el mayor o menor agregado, incluye la "
                        "dimensión, la métrica agregada, ordena por esa métrica (DESC o ASC) y usa "
                        "limit=1. La dimensión es obligatoria: una pregunta por qué eventos, "
                        "departamento o entidad no se responde con un agregado global sin agrupar. "
                        "No sustituyas SUM por MAX para resolver un ranking. En LOOKUP "
                        "devuelve sólo columnas necesarias para responder. Si una ejecución anual "
                        "tiene registros periódicos, selecciona determinísticamente el registro de "
                        "cierre mediante la columna temporal ordenada DESC y limit=1; no sumes "
                        "snapshots acumulados. Aplica los calificadores categóricos presentes en "
                        "la intención y, para totales sectoriales, la categoría total o de "
                        "funcionamiento que describa el registro agregado."
                        + (
                            " Puedes proponer textual_requests usando solo índices, filas, "
                            "operaciones y parámetros cerrados. Esa propuesta no certifica "
                            "existencia, elegibilidad, privacidad, orden total, ausencia de "
                            "empates, resultado ni persistencia: el código lo comprobará. "
                            "Para first_by_validated_order solicita limit>=2 y ordena por "
                            "todas las salidas para permitir comprobar un ganador único."
                            if settings.deterministic_textual_facts_enabled
                            else ""
                        )
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
        if isinstance(selection, EnumeratedPlanSelection):
            return selection
        return EnumeratedPlanSelection.model_validate(selection.model_dump())

    async def explore(profile, selection, explored, max_tool_calls):
        # RNF-002: `explorar_valores` puede probar hasta tres variantes, pero
        # cada una es una llamada real y debe respetar el saldo del supervisor.
        if max_tool_calls <= 0:
            raise ValueError("no queda presupuesto para explorar valores")
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
        terms = _exploration_terms(proposed, min(3, max_tool_calls))
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
                code = str(error.get("code") or "EXPLORATION_ERROR")
                message = str(error.get("message") or "falló explorar_valores")
                if code in {"SOCRATA_TIMEOUT", "SOCRATA_ERROR"}:
                    raise DeterministicToolInfrastructureError(code, message)
                raise ValueError(message)
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
            textual_facts_enabled=settings.deterministic_textual_facts_enabled,
            is_cancelled=is_cancelled,
        )

    async def synthesize(intent, claims):
        requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
        indexed = list(enumerate(claims.claims))
        relevant = [
            (index, claim)
            for index, claim in indexed
            if claim_is_relevant_to_narrative(
                claim.public_columns, requested_tokens=requested_tokens
            )
        ]
        pool = relevant if relevant else indexed
        claim_view = [
            {
                "claim_index": index,
                "description": claim.description,
                "display_value": claim.display_value,
                "unit": claim.unit,
                "label": claim.label,
                "label_status": claim.label_status,
            }
            for index, claim in pool
        ]
        return await _invoke(
            synthesis_model,
            GroundedSynthesis,
            [
                SystemMessage(
                    content=(
                        "Redacta una respuesta clara usando solo los claims enumerados. Toda "
                        "respuesta debe citar como máximo 12 claims y priorizar los que contestan "
                        "directamente la pregunta. Cada "
                        "cifra debe copiar un display_value citado. Usa exactamente el texto de "
                        "'label' para describir cada cifra citada cuando 'label_status' sea "
                        "'verified', colocando la etiqueta junto a su propio valor sin "
                        "intercambiarla con la de otro claim. Si 'label_status' es 'ambiguous', "
                        "menciona la cifra sin inventar una categoría para ella. No agregues "
                        "cálculos, fechas, porcentajes ni cantidades que no estén en esos claims."
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

    async def plan_synthesis(
        intent,
        allowed: AllowedGroundedFacts,
    ) -> GroundedSynthesisPlan:
        if synthesis_plan_model is None:
            raise RuntimeError("el plan de síntesis cerrada requiere el flag textual")
        # RF-212 (T-617C-R1): el LLM solo ve hechos cuantitativos relevantes
        # para la intención (identificadores/dimensiones auxiliares fuera
        # salvo solicitud explícita); la validación posterior sigue
        # certificando contra el conjunto completo `allowed`.
        requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
        visible_facts = tuple(
            fact
            for fact in allowed.facts
            if not isinstance(fact, AllowedQuantitativeFact)
            or claim_is_relevant_to_narrative(fact.columns, requested_tokens=requested_tokens)
        )
        visible = allowed.model_copy(update={"facts": visible_facts or allowed.facts})
        return await _invoke(
            synthesis_plan_model,
            GroundedSynthesisPlan,
            [
                SystemMessage(
                    content=(
                        "Devuelve únicamente grounded-synthesis-plan-v1. Puedes elegir y ordenar "
                        "IDs persistidos, plantillas y conectores del esquema; no redactes texto, "
                        "no copies valores, no calcules, no agregues referencias y no alteres "
                        "identificadores. El primer segmento usa sin_conector y los posteriores "
                        "un conector explícito. comparison_pair solo relaciona dos referencias "
                        "distintas de la misma evidencia."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "intent": intent.model_dump(mode="json"),
                            "allowed_grounded_facts": visible.model_dump(mode="json"),
                        },
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
        plan_synthesis=(plan_synthesis if settings.deterministic_textual_facts_enabled else None),
    )
