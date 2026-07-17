"""Puerta T-611: aceptación E2E productiva del runtime determinista.

Entra EXCLUSIVAMENTE por ``execute_deterministic_agent_run_async``
(``app.agent.runner``), la función real que ``execute_agent_run_async``
despacha cuando ``AGENT_RUNTIME=deterministic``. Ninguna prueba de este
archivo importa ``app.agent.graph``, ``build_graph`` ni ``initial_state``
(runtime legado, congelado — ``research.md`` §25).

Dos niveles de aceptación conviven en este archivo (ronda de revisión,
Corrección 2):

1. **Historias 1-9**: aceptación de la MÁQUINA con dependencias guionadas.
   Reemplazan ``app.agent.runner.build_real_runtime_dependencies`` por
   completo con closures puras por historia, para aislar transiciones del
   supervisor (``deterministic_graph.py``/``deterministic_runtime.py``) sin
   gastar cuota de proveedores. T5→T6→T7 (``execute_validated_plan``,
   ``build_claims``, ``validate_evidence``) SÍ se ejecutan de verdad.
2. **Historia 10**: aceptación del ENSAMBLAJE PRODUCTIVO. Deja correr
   ``build_real_runtime_dependencies`` REAL (verificado con un spy que envuelve
   la función real, no la reemplaza) y solo sustituye sus bordes externos
   inevitables: el ``Runnable`` de salida estructurada LLM, el cliente de
   embeddings y el transporte HTTP hacia Socrata. Demuestra que la fábrica
   productiva ensambla adaptadores que conectan de verdad intención →
   recuperación (pgvector real) → perfilado (Postgres real) → planificación →
   ejecución → calidad → claims → síntesis/persistencia.

PostgreSQL es real (``DATABASE_URL`` del proceso, no de ``backend/.env``: las
pruebas de integración de este repositorio leen ``os.environ`` de forma
directa).

Aislamiento de datos (ronda de revisión, Corrección 1): cada prueba genera
identificadores propios (``run_id`` UUID; ``dataset_id`` con sufijo aleatorio)
y los registra en el fixture ``created``. El teardown de ``created`` borra
EXCLUSIVAMENTE esos identificadores por igualdad exacta — nunca por prefijo o
``LIKE`` — y se ejecuta en el ``finally`` del fixture, por lo que corre aunque
la prueba falle. No existe limpieza preventiva por prefijo al iniciar la
suite: como los identificadores son únicos por ejecución, no hace falta.
``test_zz_sentinel_dataset_survived_every_teardown_in_this_module`` (al final
de este archivo) comprueba con una fila centinela ajena a todos los casos que
ningún teardown de esta suite borra datos que no creó.
"""

from __future__ import annotations

import json
import os
import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agent.deterministic_dependencies as deterministic_dependencies_module
from app.agent.deterministic_pipeline import (
    ExecutionMetadata,
    execute_validated_plan,
)
from app.agent.deterministic_runtime import (
    DeterministicRuntimeDependencies,
    ExploredColumnValues,
    ProfiledCandidate,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    MetricChoice,
    QuantitativePlanSelection,
)
from app.agent.multiquery_retrieval import MultiQueryRetrievalResult, RetrievedCandidate
from app.agent.plan_validator import ObservedColumn, ObservedDatasetSchema
from app.agent.query_plan import (
    ArgmaxLabelSelection,
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DatasetOption,
    DirectTextSelection,
    EligibilityStatus,
    FilterOperator,
    PiiRiskLevel,
    QueryOperation,
    ScalarType,
)
from app.agent.runner import execute_deterministic_agent_run_async
from app.catalog.embeddings import EMBEDDING_DIMENSION, EXPECTED_EMBEDDING_MODEL
from app.catalog.search import CatalogSearchItem
from app.config import Settings, normalize_database_url_for_sqlalchemy
from app.db.models import (
    AgentRun,
    AgentRunEvent,
    AgentStep,
    CatalogColumn,
    CatalogDataset,
    CatalogEmbedding,
    EvidenceResult,
    QualityReport,
    QuantitativeClaim,
)
from app.db.models import (
    TextualFact as TextualFactRecord,
)
from app.llm.factory import LLMProviderError
from app.quality.textual_fact_builder import TextualFactError

pytestmark = [pytest.mark.integration, pytest.mark.deterministic_agent_acceptance]

QUESTION_PREFIX = "T-611 "

_CATEGORIA_MONTO_COLUMNS = (
    ("categoria", ColumnDataType.TEXT, PiiRiskLevel.LOW),
    ("monto", ColumnDataType.NUMBER, PiiRiskLevel.LOW),
)
_MUNICIPIO_MONTO_COLUMNS = (
    ("municipio", ColumnDataType.TEXT, PiiRiskLevel.LOW),
    ("monto", ColumnDataType.NUMBER, PiiRiskLevel.LOW),
)


def _fresh_dataset_id() -> str:
    """Identificador único por ejecución (patrón Socrata `xxxx-xxxx`).

    Nunca un literal fijo: la Corrección 1 exige que la limpieza sea por
    identificador exacto, no por prefijo, y que la suite tolere ejecución
    repetida y casos concurrentes sin colisionar entre corridas.
    """

    return f"{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[4:8]}"


def settings(**overrides: object) -> Settings:
    """Aísla `Settings` del `.env` local real (mismo hallazgo documentado en
    `tests/test_settings.py::settings`): las pruebas de integración exportan
    `DATABASE_URL` en el proceso, nunca dependen de secretos de proveedor
    reales porque las dependencias LLM/embeddings/Socrata se reemplazan por
    completo (historias 1-9) o solo en sus bordes externos (historia 10)."""

    values: dict[str, object] = {
        "DATABASE_URL": os.environ["DATABASE_URL"],
        "EMBEDDING_MODEL": "gemini-embedding-2",
        "AGENT_RUNTIME": "deterministic",
        "LLM_PROVIDER": "google",
        "LLM_MODEL": "gemini-2.5-flash",
        "RUN_MAX_DURATION_S": 600,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _InertEmbeddingClient:
    """Reemplazo de `GoogleGenerativeAIEmbeddings` para las historias 1-9:
    `runner.py` lo construye incondicionalmente antes de invocar la fábrica
    de dependencias, pero ninguna dependencia guionada de esas historias
    llama `.aembed_query` nunca (la fábrica entera está reemplazada)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


def _dependencies_factory(dependencies: DeterministicRuntimeDependencies):
    """Sustituye `app.agent.runner.build_real_runtime_dependencies` (historias
    1-9): ignora los adaptadores productivos (settings/engine/http_client/
    embedding_client/usage) y devuelve las closures deterministas fijadas por
    la historia."""

    def _build(**_kwargs: object) -> DeterministicRuntimeDependencies:
        return dependencies

    return _build


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch, dependencies: DeterministicRuntimeDependencies
) -> None:
    monkeypatch.setattr("app.agent.runner.GoogleGenerativeAIEmbeddings", _InertEmbeddingClient)
    monkeypatch.setattr(
        "app.agent.runner.build_real_runtime_dependencies",
        _dependencies_factory(dependencies),
    )


# --- Helpers de catálogo y de corrida (historias 1-9) -----------------------


def _search_item(dataset_id: str) -> CatalogSearchItem:
    now = datetime.now(UTC)
    return CatalogSearchItem(
        dataset_id=dataset_id,
        name=f"Dataset de prueba {dataset_id}",
        publisher="Entidad Oficial de Prueba",
        official_publisher_id=None,
        publisher_verification_status="verified",
        pii_risk_level="low",
        eligibility_status="eligible",
        eligibility_reasons=[],
        similarity=0.91,
        row_count=100,
        data_updated_at=now,
        latest_observed_cutoff_at=None,
        metadata_synced_at=now,
        index_stale=False,
        columns_preview=["categoria", "monto"],
        columns_all=["categoria", "monto"],
    )


def _candidate(dataset_id: str, *, best_rank: int = 0) -> RetrievedCandidate:
    return RetrievedCandidate(
        item=_search_item(dataset_id),
        score=1.0,
        matched_queries=("consulta de prueba",),
        best_rank=best_rank,
    )


def _profile(
    dataset_id: str,
    columns_spec: tuple[tuple[str, ColumnDataType, PiiRiskLevel], ...],
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    dataset_pii: PiiRiskLevel = PiiRiskLevel.LOW,
) -> ProfiledCandidate:
    options = tuple(
        ColumnOption(
            index=index,
            field_name=name,
            display_name=name.replace("_", " ").capitalize(),
            data_type=data_type,
            pii_risk_level=pii,
        )
        for index, (name, data_type, pii) in enumerate(columns_spec)
    )
    observed = tuple(
        ObservedColumn(field_name=name, data_type=data_type, pii_risk_level=pii)
        for name, data_type, pii in columns_spec
    )
    return ProfiledCandidate(
        option=DatasetOption(
            index=0,
            dataset_id=dataset_id,
            title=f"Dataset de prueba {dataset_id}",
            publisher="Entidad Oficial de Prueba",
            columns=options,
        ),
        schema=ObservedDatasetSchema(
            dataset_id=dataset_id,
            eligibility_status=eligibility,
            pii_risk_level=dataset_pii,
            columns=observed,
        ),
    )


def _sum_selection(
    *,
    metric_column_index: int,
    filters: tuple[FilterChoice, ...] = (),
) -> EnumeratedPlanSelection:
    return EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=metric_column_index),),
        filters=filters,
        order_by=(),
        limit=100,
        needs_value_exploration=False,
    )


def _executor(rows: list[dict], *, source_url: str = "https://www.datos.gov.co/d/test-0000"):
    calls: list[dict] = []

    async def execute(payload: dict) -> dict:
        calls.append(payload)
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": rows,
            "source_url": source_url,
            "row_count": len(rows),
        }

    return execute, calls


def _metadata(
    *,
    dataset_name: str = "Dataset de prueba",
    dataset_pii_risk_level: str = "low",
    dataset_eligibility_status: str = "eligible",
    dataset_eligibility_reasons: tuple[str, ...] = (),
) -> ExecutionMetadata:
    return ExecutionMetadata(
        dataset_name=dataset_name,
        publisher="Entidad Oficial de Prueba",
        dataset_pii_risk_level=dataset_pii_risk_level,
        dataset_eligibility_status=dataset_eligibility_status,
        dataset_eligibility_reasons=dataset_eligibility_reasons,
        data_updated_at=None,
        official_publisher_id=None,
    )


# --- Registro exacto de filas creadas y limpieza (Corrección 1) ------------


@dataclass
class _CreatedIds:
    """Identificadores exactos creados por UNA prueba. El teardown de
    `created` borra únicamente estos — nunca por prefijo ni `LIKE`."""

    run_ids: list[uuid.UUID] = field(default_factory=list)
    dataset_ids: list[str] = field(default_factory=list)


async def _seed_dataset(
    engine,
    created: _CreatedIds,
    *,
    dataset_id: str,
    columns: tuple[tuple[str, str], ...],
    pii_risk_level: str = "low",
    eligibility_status: str = "eligible",
) -> None:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            CatalogDataset(
                id=dataset_id,
                name=f"Dataset de prueba {dataset_id}",
                publisher="Entidad Oficial de Prueba",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                data_updated_at=now,
                api_active=True,
                pii_risk_level=pii_risk_level,
                eligibility_status=eligibility_status,
                eligibility_reasons=[],
            )
        )
        await session.flush()
        for field_name, data_type in columns:
            session.add(
                CatalogColumn(
                    dataset_id=dataset_id,
                    field_name=field_name,
                    display_name=field_name.replace("_", " ").capitalize(),
                    data_type=data_type,
                    pii_risk_level="low",
                    eligibility_status="eligible",
                    eligibility_reasons=[],
                )
            )
    created.dataset_ids.append(dataset_id)


async def _seed_run(engine, created: _CreatedIds, *, question: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question=question,
                status="running",
                worker_instance_id=None,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash="x" * 64,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class="user",
                created_at=now,
            )
        )
    created.run_ids.append(run_id)
    return run_id


async def _load_run(engine, run_id: uuid.UUID) -> AgentRun:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        run = await session.get(AgentRun, run_id)
        assert run is not None
        return run


async def _load_steps(engine, run_id: uuid.UUID) -> list[AgentStep]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(AgentStep)
                    .where(AgentStep.run_id == run_id)
                    .order_by(AgentStep.step_number)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def _load_events(engine, run_id: uuid.UUID) -> list[AgentRunEvent]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(AgentRunEvent)
                    .where(AgentRunEvent.run_id == run_id)
                    .order_by(AgentRunEvent.seq)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def _count_evidence(engine, run_id: uuid.UUID) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (await session.execute(select(EvidenceResult).where(EvidenceResult.run_id == run_id)))
            .scalars()
            .all()
        )
        return len(rows)


async def _count_quality_reports(engine, run_id: uuid.UUID) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(QualityReport)
                    .join(EvidenceResult, EvidenceResult.id == QualityReport.evidence_id)
                    .where(EvidenceResult.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        return len(rows)


async def _count_claims(engine, run_id: uuid.UUID) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(QuantitativeClaim).where(QuantitativeClaim.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        return len(rows)


async def _load_textual_facts(engine, run_id: uuid.UUID) -> list[TextualFactRecord]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(TextualFactRecord).where(TextualFactRecord.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def _assert_budgets_respected(step_events: list[AgentRunEvent]) -> None:
    """Ningún presupuesto persistido excede su máximo hardcodeado en
    `execute_deterministic_agent_run_async` (candidatos=8, exploraciones=6,
    consultas=6, reparaciones=2, llamadas LLM=10)."""

    for event in step_events:
        usage = event.payload["detail"]["usage"]
        assert usage["candidates"] <= 8, event.payload
        assert usage["explorations"] <= 6, event.payload
        assert usage["queries"] <= 6, event.payload
        assert usage["plan_repairs"] <= 2, event.payload
        assert usage["llm_calls"] <= 10, event.payload


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
async def engine():
    database = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
    )
    yield database
    await database.dispose()


@pytest.fixture
async def created(engine):
    """Corrección 1: registro exacto de `run_id`/`dataset_id` creados por la
    prueba que use este fixture. Sin limpieza preventiva por prefijo al
    entrar (los identificadores son únicos por ejecución, ver
    `_fresh_dataset_id`); el teardown borra EXCLUSIVAMENTE lo registrado, por
    igualdad exacta (`= ANY(:ids)`), respetando el orden de FKs
    (`agent_runs` primero — cascada evidence_results/quality_reports/
    quantitative_claims/agent_steps/agent_run_events — y `catalog_datasets`
    después — cascada catalog_columns/catalog_embeddings). Corre en un
    `finally`, así que se ejecuta aunque la prueba falle."""

    registry = _CreatedIds()
    try:
        yield registry
    finally:
        async with engine.begin() as conn:
            if registry.run_ids:
                await conn.execute(
                    text("DELETE FROM agent_runs WHERE id = ANY(:ids)"),
                    {"ids": registry.run_ids},
                )
            if registry.dataset_ids:
                await conn.execute(
                    text("DELETE FROM catalog_datasets WHERE id = ANY(:ids)"),
                    {"ids": registry.dataset_ids},
                )


# --- Historia 1: camino positivo completo -----------------------------------


async def test_h1_positive_path_completes_with_evidence_quality_claims_and_single_terminal(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine, created, dataset_id=dataset_id, columns=(("categoria", "Text"), ("monto", "Number"))
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 1: camino positivo completo"
    )

    executor, calls = _executor([{"metric_sum_1": "1250.50"}])

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        assert dataset == dataset_id
        return _profile(dataset_id, columns)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return _sum_selection(metric_column_index=1)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 1 no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        assert claims.claims
        display = claims.claims[0].display_value
        return GroundedSynthesis(
            answer=f"El monto observado en el conjunto de prueba fue {display}.",
            cited_claim_indexes=(0,),
        )

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    assert "final_answer" in result
    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    assert len(final_answer["evidence"]) == 1
    assert len(final_answer["claims"]) == 1
    assert calls, "el executor SoQL falso debe haberse invocado exactamente una vez"
    assert len(calls) == 1

    run = await _load_run(engine, run_id)
    assert run.status == "completed"
    assert run.terminal_error_code is None

    steps = await _load_steps(engine, run_id)
    nodes = [step.node for step in steps]
    assert nodes == [
        "select_candidate",
        "profile_dataset",
        "build_plan",
        "execute_query",
        "synthesize",
        "complete",
    ]
    events = await _load_events(engine, run_id)
    terminal_events = [event for event in events if event.event_type in ("answer", "error")]
    assert len(terminal_events) == 1
    assert terminal_events[0].event_type == "answer"

    assert await _count_evidence(engine, run_id) == 1
    assert await _count_quality_reports(engine, run_id) == 1
    assert await _count_claims(engine, run_id) == 1

    _assert_budgets_respected([event for event in events if event.event_type == "step"])


async def test_t615f_text_is_persisted_internally_without_public_api_or_legacy(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = (("municipio", ColumnDataType.TEXT, PiiRiskLevel.LOW),)
    await _seed_dataset(
        engine,
        created,
        dataset_id=dataset_id,
        columns=(("municipio", "Text"),),
    )
    run_id = await _seed_run(
        engine,
        created,
        question=f"{QUESTION_PREFIX}hecho textual interno verificable",
    )
    executor, calls = _executor([{"dim_1": "  Medellín  "}])

    async def extract_intent(_question: str) -> IntentExtraction:
        return IntentExtraction(topic="municipio observado", operation=QueryOperation.LOOKUP)

    async def retrieve(_intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("municipio",),
            candidates=(_candidate(dataset_id),),
        )

    async def profile(_dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns)

    async def plan(_intent, _context, _explored, _error) -> EnumeratedPlanSelection:
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.LOOKUP,
            dimension_column_indexes=(0,),
            textual_requests=(
                DirectTextSelection(
                    source_row_indexes=(0,),
                    column=ColumnReference(column_index=0),
                ),
            ),
            limit=2,
        )

    async def explore(*_args):
        raise AssertionError("el caso textual no requiere exploración")

    async def execute(validated):
        return await execute_validated_plan(
            validated,
            executor=executor,
            metadata=_metadata(),
            textual_facts_enabled=True,
        )

    async def synthesize(*_args):
        raise AssertionError("T-615F no debe sintetizar hechos textuales")

    _patch_runtime(
        monkeypatch,
        DeterministicRuntimeDependencies(
            extract_intent=extract_intent,
            retrieve=retrieve,
            profile=profile,
            plan=plan,
            explore=explore,
            execute=execute,
            synthesize=synthesize,
        ),
    )
    monkeypatch.setattr(
        "app.agent.runner.execute_legacy_agent_run_async",
        lambda *_args, **_kwargs: pytest.fail("el runtime legacy no debe invocarse"),
    )

    result = await execute_deterministic_agent_run_async(
        settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=True),
        run_id,
    )

    assert len(calls) == 1
    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["evidence"] == []
    assert final_answer["claims"] == []
    assert "textual_facts" not in final_answer
    assert "Medellín" not in json.dumps(final_answer, ensure_ascii=False)

    facts = await _load_textual_facts(engine, run_id)
    assert len(facts) == 1
    assert facts[0].operation == "direct_text"
    assert facts[0].raw_values == ["  Medellín  "]
    assert facts[0].display_value == "Medellín"
    assert await _count_evidence(engine, run_id) == 1
    assert await _count_quality_reports(engine, run_id) == 1
    assert await _count_claims(engine, run_id) == 0

    nodes = [step.node for step in await _load_steps(engine, run_id)]
    assert nodes[-1] == "abstain"
    assert "synthesize" not in nodes
    events = await _load_events(engine, run_id)
    assert len([event for event in events if event.event_type in ("answer", "error")]) == 1
    _assert_budgets_respected([event for event in events if event.event_type == "step"])


async def test_t615f_textual_persistence_failure_downgrades_public_success_without_losing_claims(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine,
        created,
        dataset_id=dataset_id,
        columns=(("categoria", "Text"), ("monto", "Number")),
    )
    run_id = await _seed_run(
        engine,
        created,
        question=f"{QUESTION_PREFIX}fallo textual no es éxito narrativo",
    )
    executor, _calls = _executor(
        [
            {"dim_1": "Bogotá", "metric_sum_1": "20"},
            {"dim_1": "Medellín", "metric_sum_1": "10"},
        ]
    )

    async def extract_intent(_question: str) -> IntentExtraction:
        return IntentExtraction(topic="mayor monto por categoría", operation=QueryOperation.SUM)

    async def retrieve(_intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("monto",),
            candidates=(_candidate(dataset_id),),
        )

    async def profile(_dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns)

    async def plan(_intent, _context, _explored, _error) -> EnumeratedPlanSelection:
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            dimension_column_indexes=(0,),
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
            textual_requests=(
                ArgmaxLabelSelection(
                    source_row_indexes=(0, 1),
                    label_column=ColumnReference(column_index=0),
                    metric_column=ColumnReference(column_index=1),
                ),
            ),
            limit=2,
        )

    async def explore(*_args):
        raise AssertionError("el caso mixto no requiere exploración")

    async def execute(validated):
        return await execute_validated_plan(
            validated,
            executor=executor,
            metadata=_metadata(),
            textual_facts_enabled=True,
        )

    async def synthesize(_intent, claims) -> GroundedSynthesis:
        return GroundedSynthesis(
            answer=f"El monto observado fue {claims.claims[0].display_value}.",
            cited_claim_indexes=(0,),
        )

    async def fail_textual_batch(*_args, **_kwargs):
        raise TextualFactError("textual_persistence_failed", "rollback del lote")

    _patch_runtime(
        monkeypatch,
        DeterministicRuntimeDependencies(
            extract_intent=extract_intent,
            retrieve=retrieve,
            profile=profile,
            plan=plan,
            explore=explore,
            execute=execute,
            synthesize=synthesize,
        ),
    )
    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.build_verify_persist_textual_facts",
        fail_textual_batch,
    )
    monkeypatch.setattr(
        "app.agent.runner.execute_legacy_agent_run_async",
        lambda *_args, **_kwargs: pytest.fail("el runtime legacy no debe invocarse"),
    )

    result = await execute_deterministic_agent_run_async(
        settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=True),
        run_id,
    )
    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["narrative"] is None
    assert final_answer["claims"] == []
    assert final_answer["evidence"] == []
    assert await _count_evidence(engine, run_id) == 1
    assert await _count_claims(engine, run_id) == 2
    assert await _load_textual_facts(engine, run_id) == []


# --- Historia 2: cambio de candidato -----------------------------------------


async def test_h2_first_candidate_rejected_second_candidate_completes_without_early_termination(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    rejected_id = _fresh_dataset_id()
    accepted_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine,
        created,
        dataset_id=accepted_id,
        columns=(("categoria", "Text"), ("monto", "Number")),
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 2: cambio de candidato"
    )

    executor, calls = _executor([{"metric_sum_1": "42.0"}])
    profiled_order: list[str] = []

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("prueba",),
            candidates=(_candidate(rejected_id, best_rank=0), _candidate(accepted_id, best_rank=1)),
        )

    async def profile(dataset: str) -> ProfiledCandidate:
        profiled_order.append(dataset)
        if dataset == rejected_id:
            return _profile(rejected_id, columns, eligibility=EligibilityStatus.DIAGNOSTIC_ONLY)
        return _profile(accepted_id, columns, eligibility=EligibilityStatus.ELIGIBLE)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return _sum_selection(metric_column_index=1)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 2 no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        display = claims.claims[0].display_value
        return GroundedSynthesis(answer=f"El monto fue {display}.", cited_claim_indexes=(0,))

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    assert final_answer["evidence"][0]["dataset_id"] == accepted_id
    assert profiled_order == [rejected_id, accepted_id]
    assert len(calls) == 1, "solo el segundo candidato debe llegar a ejecutar SoQL"

    steps = await _load_steps(engine, run_id)
    select_steps = [step for step in steps if step.node == "select_candidate"]
    assert len(select_steps) == 2, "debe seleccionar dos candidatos distintos, sin terminar antes"
    assert [step.node for step in steps][-1] == "complete"

    events = await _load_events(engine, run_id)
    terminal_events = [event for event in events if event.event_type in ("answer", "error")]
    assert len(terminal_events) == 1
    _assert_budgets_respected([event for event in events if event.event_type == "step"])


# --- Historia 3: reparación de plan -------------------------------------------


async def test_h3_first_invalid_plan_is_typed_and_repaired_within_budget_no_invalid_soql_runs(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine, created, dataset_id=dataset_id, columns=(("categoria", "Text"), ("monto", "Number"))
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 3: reparación de plan"
    )

    executor, calls = _executor([{"metric_sum_1": "77.0"}])
    plan_calls: list[str | None] = []

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        plan_calls.append(None if validation_error is None else validation_error.code.value)
        if validation_error is None:
            # primer intento: referencia una columna inexistente (99)
            return _sum_selection(metric_column_index=99)
        # segundo intento: plan corregido, columna real (1 = monto)
        return _sum_selection(metric_column_index=1)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 3 no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        display = claims.claims[0].display_value
        return GroundedSynthesis(answer=f"El monto fue {display}.", cited_claim_indexes=(0,))

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    assert len(plan_calls) == 2, "debe reparar exactamente una vez dentro del presupuesto"
    assert plan_calls[0] is None
    assert plan_calls[1] == "UNKNOWN_REFERENCE"
    assert len(calls) == 1, "el SoQL inválido (columna 99) nunca debe llegar al ejecutor"

    steps = await _load_steps(engine, run_id)
    build_plan_steps = [step for step in steps if step.node == "build_plan"]
    assert len(build_plan_steps) == 2
    assert build_plan_steps[0].display_message == "falta plan tipado"
    # el código tipado del error solo se anota en la reparación (segundo
    # intento); el primer BUILD_PLAN todavía no tiene `validation_error`.
    assert "UNKNOWN_REFERENCE" in (build_plan_steps[1].display_message or "")

    events = await _load_events(engine, run_id)
    _assert_budgets_respected([event for event in events if event.event_type == "step"])


# --- Historia 4: exploración categórica --------------------------------------


async def test_h4_single_pending_categorical_column_is_resolved_without_repeated_exploration(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine, created, dataset_id=dataset_id, columns=(("categoria", "Text"), ("monto", "Number"))
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 4: exploración categórica"
    )

    executor, calls = _executor([{"metric_sum_1": "310.0"}])
    explore_calls: list[str] = []

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        if explored:
            confirmed = explored[0].values[0]
            filters = (
                FilterChoice(
                    column_index=0,
                    operator=FilterOperator.EQ,
                    value_type=ScalarType.TEXT,
                    values=(confirmed,),
                ),
            )
        else:
            filters = (
                FilterChoice(
                    column_index=0,
                    operator=FilterOperator.EQ,
                    value_type=ScalarType.TEXT,
                    values=("pendiente-de-confirmar",),
                ),
            )
        return _sum_selection(metric_column_index=1, filters=filters)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        explore_calls.append(selection.filters[0].values[0])
        return ExploredColumnValues(
            column_index=0,
            search_term=selection.filters[0].values[0],
            values=("CONFIRMADO",),
            tool_calls=1,
        )

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        display = claims.claims[0].display_value
        return GroundedSynthesis(answer=f"El monto fue {display}.", cited_claim_indexes=(0,))

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    assert len(explore_calls) == 1, "no debe repetir exploración innecesariamente"
    assert len(calls) == 1
    assert "CONFIRMADO" in calls[0]["soql"]

    steps = await _load_steps(engine, run_id)
    assert [step.node for step in steps].count("explore_value") == 1

    events = await _load_events(engine, run_id)
    _assert_budgets_respected([event for event in events if event.event_type == "step"])


# --- Historia 5: privacidad ----------------------------------------------------


async def test_h5a_high_pii_dataset_is_rejected_before_any_query(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = (("nombre_completo", ColumnDataType.TEXT, PiiRiskLevel.HIGH),)
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 5a: PII alta rechazada"
    )

    executor, calls = _executor([{"metric_count_1": "1"}])

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="conteo de registros", operation=QueryOperation.COUNT)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns, dataset_pii=PiiRiskLevel.HIGH)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.COUNT,
            dimension_column_indexes=(),
            metrics=(MetricChoice(operation=QueryOperation.COUNT, column_index=None),),
            filters=(),
            order_by=(),
            limit=100,
            needs_value_exploration=False,
        )

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 5a no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 5a no debe llegar a síntesis")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["evidence"] == []
    assert final_answer["claims"] == []
    assert not calls, "PII alta debe rechazarse antes de cualquier consulta"
    assert await _count_evidence(engine, run_id) == 0
    assert await _count_claims(engine, run_id) == 0

    run = await _load_run(engine, run_id)
    assert run.status == "no_evidence"


async def test_h5b_medium_pii_with_insufficient_aggregation_is_rejected(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _MUNICIPIO_MONTO_COLUMNS
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 5b: PII media insegura"
    )

    # `group_count` queda en 2 (< 5): agregación insuficiente para PII medium.
    executor, calls = _executor(
        [{"dim_1": "Municipio X", "metric_sum_1": "500.0", "group_count": "2"}]
    )

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        # PII medium a nivel de esquema: `validate_query_plan` activa
        # `include_group_count`, así el SoQL renderizado agrega `count(*)`
        # de verdad y T6 puede evaluar `aggregation_min_count` sobre él.
        return _profile(dataset_id, columns, dataset_pii=PiiRiskLevel.MEDIUM)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            dimension_column_indexes=(0,),
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
            filters=(),
            order_by=(),
            limit=100,
            needs_value_exploration=False,
        )

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 5b no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(
            validated,
            executor=executor,
            metadata=_metadata(
                dataset_pii_risk_level="medium",
                dataset_eligibility_reasons=("pii_medium_requires_aggregation",),
            ),
        )

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 5b no debe llegar a síntesis")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["evidence"] == []
    assert len(calls) == 1, "T6 evalúa la evidencia antes de rechazarla (no un rechazo previo)"
    assert await _count_evidence(engine, run_id) == 0
    assert await _count_claims(engine, run_id) == 0


async def test_h5c_medium_pii_with_sufficient_aggregation_is_permitted(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _MUNICIPIO_MONTO_COLUMNS
    await _seed_dataset(
        engine, created, dataset_id=dataset_id, columns=(("municipio", "Text"), ("monto", "Number"))
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 5c: PII media agregada"
    )

    # `group_count` = 12 (>= 5): agregación suficiente, evidencia elegible.
    executor, calls = _executor(
        [{"dim_1": "Municipio X", "metric_sum_1": "500.0", "group_count": "12"}]
    )

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        # PII medium a nivel de esquema: `validate_query_plan` activa
        # `include_group_count`, así el SoQL renderizado agrega `count(*)`
        # de verdad y T6 puede evaluar `aggregation_min_count` sobre él.
        return _profile(dataset_id, columns, dataset_pii=PiiRiskLevel.MEDIUM)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            dimension_column_indexes=(0,),
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
            filters=(),
            order_by=(),
            limit=100,
            needs_value_exploration=False,
        )

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 5c no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(
            validated,
            executor=executor,
            metadata=_metadata(
                dataset_pii_risk_level="medium",
                dataset_eligibility_reasons=("pii_medium_requires_aggregation",),
            ),
        )

    async def synthesize(intent, claims) -> GroundedSynthesis:
        display = claims.claims[0].display_value
        return GroundedSynthesis(
            answer=f"El monto agregado fue {display}.", cited_claim_indexes=(0,)
        )

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    assert len(calls) == 1
    assert await _count_evidence(engine, run_id) == 1
    assert await _count_claims(engine, run_id) >= 1


# --- Historia 6: abstención segura --------------------------------------------


async def test_h6_no_candidates_abstains_honestly_without_fabricated_evidence(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 6: abstención segura"
    )

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(
            topic="tema sin datasets en el catálogo", operation=QueryOperation.SUM
        )

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba sin resultados",), candidates=())

    async def profile(dataset: str) -> ProfiledCandidate:
        raise AssertionError("historia 6 no debe perfilar ningún dataset")

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        raise AssertionError("historia 6 no debe planificar")

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 6 no debe explorar")

    async def execute(validated):
        raise AssertionError("historia 6 no debe ejecutar SoQL")

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 6 no debe sintetizar")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["evidence"] == []
    assert final_answer["claims"] == []
    assert final_answer["no_evidence_report"]["reason"] == "NO_CANDIDATES"
    assert await _count_evidence(engine, run_id) == 0
    assert await _count_claims(engine, run_id) == 0

    run = await _load_run(engine, run_id)
    assert run.status == "no_evidence"

    events = await _load_events(engine, run_id)
    terminal_events = [event for event in events if event.event_type in ("answer", "error")]
    assert len(terminal_events) == 1
    assert terminal_events[0].event_type == "answer", "no_evidence es terminal 'answer', no 'error'"


# --- Historia 7: fallo del proveedor y fallback -------------------------------


async def test_h7a_synthesis_provider_failure_falls_back_to_deterministic_synthesis(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    await _seed_dataset(
        engine, created, dataset_id=dataset_id, columns=(("categoria", "Text"), ("monto", "Number"))
    )
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 7a: fallback de síntesis"
    )

    executor, calls = _executor([{"metric_sum_1": "88.0"}])

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        return _profile(dataset_id, columns)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return _sum_selection(metric_column_index=1)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 7a no debe requerir exploración")

    async def execute(validated):
        return await execute_validated_plan(validated, executor=executor, metadata=_metadata())

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise LLMProviderError("504 The request timed out (simulado)")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed"
    fallback_prefix = "Resultados calculados con la evidencia consultada:"
    assert final_answer["narrative"].startswith(fallback_prefix)
    assert len(final_answer["claims"]) == 1

    run = await _load_run(engine, run_id)
    assert run.status == "completed"


async def test_h7b_provider_failure_outside_synthesis_terminates_controlled(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    """Nunca cae al runtime legado: termina con un código de error tipado."""

    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 7b: terminal controlado"
    )

    async def extract_intent(question: str) -> IntentExtraction:
        raise LLMProviderError("cuota agotada (simulado)")

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        raise AssertionError("historia 7b no debe recuperar candidatos")

    async def profile(dataset: str) -> ProfiledCandidate:
        raise AssertionError("historia 7b no debe perfilar")

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        raise AssertionError("historia 7b no debe planificar")

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 7b no debe explorar")

    async def execute(validated):
        raise AssertionError("historia 7b no debe ejecutar")

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 7b no debe sintetizar")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    assert "terminal_error" in result
    assert result["terminal_error"]["error"]["code"] == "LLM_PROVIDER_ERROR"
    assert result["terminal_error"]["error"]["retryable"] is False

    run = await _load_run(engine, run_id)
    assert run.status == "failed"
    assert run.terminal_error_code == "LLM_PROVIDER_ERROR"

    events = await _load_events(engine, run_id)
    terminal_events = [event for event in events if event.event_type in ("answer", "error")]
    assert len(terminal_events) == 1
    assert terminal_events[0].event_type == "error"


# --- Historia 8: cancelación cooperativa --------------------------------------


async def test_h8_cooperative_cancellation_leaves_no_completed_or_double_terminal(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    dataset_id = _fresh_dataset_id()
    columns = _CATEGORIA_MONTO_COLUMNS
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 8: cancelación cooperativa"
    )

    cancel_event = threading.Event()

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(queries=("prueba",), candidates=(_candidate(dataset_id),))

    async def profile(dataset: str) -> ProfiledCandidate:
        # simula que llega una solicitud de cancelación cooperativa (DELETE
        # sobre una corrida activa, RF-803) justo después de perfilar.
        cancel_event.set()
        return _profile(dataset_id, columns)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        raise AssertionError("la corrida debe cancelarse antes de planificar")

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 8 no debe explorar")

    async def execute(validated):
        raise AssertionError("historia 8 no debe ejecutar")

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 8 no debe sintetizar")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id, cancel_event)

    assert result == {}, "una cancelación cooperativa no produce final_answer ni terminal_error"

    run = await _load_run(engine, run_id)
    assert run.status == "running", "sin borrado explícito, la corrida cancelada sigue 'running'"
    assert run.terminal_error_code is None

    steps = await _load_steps(engine, run_id)
    nodes = [step.node for step in steps]
    assert "select_candidate" in nodes
    assert "profile_dataset" in nodes
    assert "complete" not in nodes
    assert "synthesize" not in nodes

    events = await _load_events(engine, run_id)
    terminal_events = [event for event in events if event.event_type in ("answer", "error")]
    assert len(terminal_events) == 0, (
        "cero eventos terminales; el borrado (RF-803) es responsabilidad del DELETE"
    )


# --- Historia 9: presupuesto de candidatos ------------------------------------
#
# CORRECCIÓN 3 (ronda de revisión): el bloque siguiente documenta un
# DEFECTO/AMBIGÜEDAD PRODUCTIVA PENDIENTE, no una protección correcta. No se
# modifica `deterministic_runtime.py` ni `deterministic_graph.py` en esta
# ronda (fuera de alcance; requiere autorización explícita del coordinador
# antes de T-614, research.md §25). Se conserva una prueba que reproduce el
# comportamiento ACTUAL y se añade una prueba `xfail(strict=True)` que
# expresa la semántica ESPERADA (ocho candidatos permitidos implican hasta
# ocho candidatos perfilados) y que falla contra el comportamiento actual.


async def _run_h9_candidate_budget_scenario(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> tuple[dict, list[str], list[str], list[AgentRunEvent], uuid.UUID]:
    dataset_ids = [_fresh_dataset_id() for _ in range(8)]
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 9: presupuesto de candidatos"
    )

    columns = _CATEGORIA_MONTO_COLUMNS
    profiled: list[str] = []

    async def extract_intent(question: str) -> IntentExtraction:
        return IntentExtraction(topic="monto observado", operation=QueryOperation.SUM)

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("prueba",),
            candidates=tuple(
                _candidate(dataset_id, best_rank=index)
                for index, dataset_id in enumerate(dataset_ids)
            ),
        )

    async def profile(dataset: str) -> ProfiledCandidate:
        profiled.append(dataset)
        # todos los candidatos quedan no elegibles: rechazo inmediato de un
        # solo intento por candidato (sin gastar presupuesto de reparación).
        return _profile(dataset, columns, eligibility=EligibilityStatus.DIAGNOSTIC_ONLY)

    async def plan(intent, context, explored, validation_error) -> EnumeratedPlanSelection:
        return _sum_selection(metric_column_index=1)

    async def explore(profile_arg, selection, explored) -> ExploredColumnValues:
        raise AssertionError("historia 9 no debe requerir exploración")

    async def execute(validated):
        raise AssertionError("ningún candidato debe llegar a ejecutar SoQL")

    async def synthesize(intent, claims) -> GroundedSynthesis:
        raise AssertionError("historia 9 no debe sintetizar")

    dependencies = DeterministicRuntimeDependencies(
        extract_intent=extract_intent,
        retrieve=retrieve,
        profile=profile,
        plan=plan,
        explore=explore,
        execute=execute,
        synthesize=synthesize,
    )
    _patch_runtime(monkeypatch, dependencies)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    events = await _load_events(engine, run_id)
    step_events = [event for event in events if event.event_type == "step"]
    return result, profiled, dataset_ids, step_events, run_id


async def test_h9_candidate_budget_off_by_one_defect_documents_current_behavior(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    """DEFECTO/AMBIGÜEDAD PRODUCTIVA PENDIENTE — documenta, no certifica.

    `usage.candidates` (deterministic_graph.py `SupervisorSnapshot`/
    `_budget_stop`) cuenta un candidato como "gastado" en cuanto pasa a
    SELECTED, no cuando termina de procesarse. Con `max_candidates=8`
    (hardcodeado en `execute_deterministic_agent_run_async`), eso significa
    que el 8º candidato se selecciona pero el presupuesto ya aparece
    agotado en la siguiente iteración, así que NUNCA llega a perfilarse:
    de ocho candidatos nominalmente permitidos, solo siete se perfilan y
    rechazan por completo. No está autorizado concluir que esto es
    normativamente correcto (puede ser un off-by-one productivo). La
    corrección de runtime, si procede, es una tarea posterior autorizada
    por el coordinador — no se toca aquí. Ver también
    `test_h9_expected_semantics_eight_candidate_budget_should_allow_profiling_eight`.
    """

    result, profiled, dataset_ids, step_events, run_id = await _run_h9_candidate_budget_scenario(
        engine, monkeypatch, created
    )

    final_answer = result["final_answer"]
    assert final_answer["status"] == "no_evidence"
    assert final_answer["usage"]["termination_reason"] == "CANDIDATE_BUDGET_EXCEEDED"
    assert profiled == dataset_ids[:7], (
        "comportamiento ACTUAL (defecto/ambigüedad pendiente): el 8º candidato "
        "se selecciona pero nunca se perfila; ver docstring de esta prueba"
    )
    assert len(profiled) == 7

    _assert_budgets_respected(step_events)
    last_usage = step_events[-1].payload["detail"]["usage"]
    assert last_usage["candidates"] == 8
    assert last_usage["llm_calls"] < 10, "el presupuesto de candidatos se agota antes que el de LLM"

    assert await _count_evidence(engine, run_id) == 0
    assert await _count_claims(engine, run_id) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Defecto/ambigüedad productiva pendiente (Corrección 3, ronda de "
        "revisión T-611/T-612). Semántica ESPERADA: max_candidates=8 debería "
        "permitir perfilar hasta 8 candidatos antes de abstenerse. "
        "Comportamiento ACTUAL: `usage.candidates` cuenta un candidato como "
        "gastado en cuanto se SELECCIONA (no cuando termina de procesarse), "
        "así que el 8º candidato se selecciona pero nunca se perfila — solo "
        "7 de 8 llegan a completarse. No se corrige en esta ronda: "
        "`deterministic_runtime.py`/`deterministic_graph.py` están fuera de "
        "alcance sin autorización explícita del coordinador (research.md "
        "§25); queda como trabajo pendiente antes de usar este "
        "comportamiento para T-614. Esta prueba debe pasar a XPASS (y "
        "fallar por `strict=True`, señal correcta de que hay que quitar el "
        "marcador) el día que se corrija el runtime."
    ),
)
async def test_h9_expected_semantics_eight_candidate_budget_should_allow_profiling_eight(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    _result, profiled, dataset_ids, _step_events, _run_id = await _run_h9_candidate_budget_scenario(
        engine, monkeypatch, created
    )

    assert profiled == dataset_ids
    assert len(profiled) == 8


# --- Historia 10: ensamblaje productivo real (Corrección 2) -----------------


def _generate_unit_vector(dimension: int, seed: int) -> list[float]:
    """Vector unitario pseudoaleatorio con semilla fija — determinista entre
    corridas, pero sin sesgo hacia un eje concreto (a diferencia de un vector
    tipo `[1, 0, 0, ...]`, que podría coincidir por casualidad con la
    componente dominante de embeddings reales ya sembrados en el catálogo)."""

    rng = random.Random(seed)
    raw = [rng.uniform(-1.0, 1.0) for _ in range(dimension)]
    norm = sum(value * value for value in raw) ** 0.5
    return [value / norm for value in raw]


_ASSEMBLY_QUERY_VECTOR = _generate_unit_vector(EMBEDDING_DIMENSION, seed=611202)
_REAL_HTTPX_ASYNC_CLIENT = httpx.AsyncClient


class _RealFactoryEmbeddingClient:
    """Borde externo falso (embeddings) para la historia 10: implementa el
    protocolo `QueryEmbeddingClient` de verdad — a diferencia de
    `_InertEmbeddingClient` (historias 1-9), aquí `search_catalog` real SÍ
    llama `.aembed_query` y usa el vector devuelto contra pgvector real."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str | None = None,
        title: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[float]:
        return list(_ASSEMBLY_QUERY_VECTOR)


class _FakeStructuredModel:
    """Reemplaza el `Runnable` que produce `get_structured_chat_model` real.

    Sigue el patrón documentado en `ainvoke_structured_chat_model`
    ('los dobles de prueba pueden devolver directamente el objeto Pydantic'
    — `app/llm/factory.py`): ninguna capa intermedia necesita mockearse por
    separado, `ainvoke_structured_chat_model` real ya sabe manejar esta forma.
    """

    def __init__(self, respond) -> None:
        self._respond = respond

    async def ainvoke(self, messages, **_kwargs: object):
        return self._respond(messages)


def _fake_get_structured_chat_model(_provider: str, _model_name: str, schema, **_kwargs: object):
    if schema is IntentExtraction:
        return _FakeStructuredModel(
            lambda _messages: IntentExtraction(
                topic="ensamblaje productivo de dependencias deterministas",
                operation=QueryOperation.COUNT,
            )
        )
    if schema in {EnumeratedPlanSelection, QuantitativePlanSelection}:
        return _FakeStructuredModel(
            lambda _messages: schema(
                dataset_index=0,
                operation=QueryOperation.COUNT,
                dimension_column_indexes=(),
                metrics=(MetricChoice(operation=QueryOperation.COUNT, column_index=None),),
                filters=(),
                order_by=(),
                limit=100,
                needs_value_exploration=False,
            )
        )
    if schema is GroundedSynthesis:

        def _respond(messages) -> GroundedSynthesis:
            payload = json.loads(messages[-1].content)
            claim = payload["claims"][0]
            return GroundedSynthesis(
                answer=f"El conteo observado fue {claim['display_value']}.",
                cited_claim_indexes=(0,),
            )

        return _FakeStructuredModel(_respond)
    raise AssertionError(f"esquema de salida estructurada inesperado en la prueba: {schema!r}")


def _mock_socrata_http_client_factory(rows: list[dict]):
    """Reemplaza `httpx.AsyncClient` (global, mismo objeto de módulo que usa
    `app.agent.runner`): intercepta CUALQUIER solicitud con
    `httpx.MockTransport` real — nunca toca la red — devolviendo `rows` como
    si fueran la respuesta JSON de Socrata."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    def _factory(*_args: object, **kwargs: object) -> httpx.AsyncClient:
        return _REAL_HTTPX_ASYNC_CLIENT(
            transport=httpx.MockTransport(handler), base_url=kwargs.get("base_url")
        )

    return _factory


async def _seed_embedding(engine, *, dataset_id: str) -> None:
    """No registra en `created` por separado: `catalog_embeddings.dataset_id`
    tiene `ON DELETE CASCADE` hacia `catalog_datasets`, ya registrado por
    `_seed_dataset`."""

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            CatalogEmbedding(
                dataset_id=dataset_id,
                embedding=list(_ASSEMBLY_QUERY_VECTOR),
                model=EXPECTED_EMBEDDING_MODEL,
            )
        )


async def test_h10_real_dependency_factory_assembles_working_adapters_end_to_end(
    engine, monkeypatch: pytest.MonkeyPatch, created: _CreatedIds
) -> None:
    """Corrección 2: a diferencia de las historias 1-9 (que reemplazan
    `build_real_runtime_dependencies` por completo), esta historia deja
    correr la FÁBRICA PRODUCTIVA REAL y solo sustituye sus bordes externos
    inevitables: el `Runnable` de salida estructurada LLM
    (`get_structured_chat_model`), el cliente de embeddings y el transporte
    HTTP hacia Socrata. Demuestra que los adaptadores que ensambla la
    fábrica real conectan de verdad intención → recuperación (pgvector real)
    → perfilado (Postgres real) → planificación → ejecución (T5→T6→T7
    reales) → síntesis/persistencia, con un camino positivo completo contra
    PostgreSQL real, y confirma con un spy que la fábrica real fue invocada
    (no reemplazada)."""

    dataset_id = _fresh_dataset_id()
    await _seed_dataset(engine, created, dataset_id=dataset_id, columns=(("valor", "Number"),))
    await _seed_embedding(engine, dataset_id=dataset_id)
    run_id = await _seed_run(
        engine, created, question=f"{QUESTION_PREFIX}historia 10: ensamblaje productivo real"
    )

    http_client_factory = _mock_socrata_http_client_factory([{"metric_count_1": "42"}])

    monkeypatch.setattr(
        "app.agent.runner.GoogleGenerativeAIEmbeddings", _RealFactoryEmbeddingClient
    )
    monkeypatch.setattr("httpx.AsyncClient", http_client_factory)
    monkeypatch.setattr(
        "app.agent.deterministic_dependencies.get_structured_chat_model",
        _fake_get_structured_chat_model,
    )

    real_build_real_runtime_dependencies = (
        deterministic_dependencies_module.build_real_runtime_dependencies
    )
    factory_spy = Mock(side_effect=real_build_real_runtime_dependencies)
    monkeypatch.setattr("app.agent.runner.build_real_runtime_dependencies", factory_spy)

    result = await execute_deterministic_agent_run_async(settings(), run_id)

    # Evidencia de que la fábrica productiva REAL fue invocada (no
    # reemplazada): el spy envuelve la función real (`side_effect`), así que
    # una llamada exitosa demuestra ejecución real, no solo una interceptación.
    factory_spy.assert_called_once()
    spy_kwargs = factory_spy.call_args.kwargs
    assert isinstance(spy_kwargs["embedding_client"], _RealFactoryEmbeddingClient)
    assert spy_kwargs["engine"] is not None
    assert spy_kwargs["http_client"] is not None

    final_answer = result["final_answer"]
    assert final_answer["status"] == "completed", result
    assert len(final_answer["evidence"]) == 1
    assert final_answer["evidence"][0]["dataset_id"] == dataset_id
    assert len(final_answer["claims"]) == 1

    run = await _load_run(engine, run_id)
    assert run.status == "completed"
    assert run.terminal_error_code is None

    assert await _count_evidence(engine, run_id) == 1
    assert await _count_quality_reports(engine, run_id) == 1
    assert await _count_claims(engine, run_id) == 1

    steps = await _load_steps(engine, run_id)
    nodes = [step.node for step in steps]
    # `select_candidate`/`profile_dataset` prueban recuperación (pgvector
    # real) y perfilado (Postgres real) reales conectados de punta a punta;
    # el resto confirma que la cadena completa hasta persistencia funciona.
    assert "select_candidate" in nodes
    assert "profile_dataset" in nodes
    assert "build_plan" in nodes
    assert "execute_query" in nodes
    assert "synthesize" in nodes
    assert nodes[-1] == "complete"


# --- Preservación de datos ajenos (Corrección 1, condición 6) ---------------
#
# CORRECCIÓN (hallazgo del coordinador, ronda 2 de revisión): el diseño
# anterior declaraba `sentinel_dataset_id` como `@pytest.fixture(scope=
# "module")` SIN `autouse=True`. Un fixture de alcance módulo que no es
# autouse solo se instancia la PRIMERA VEZ que una prueba lo solicita
# explícitamente en sus parámetros — en el diseño anterior, esa prueba era
# `test_zz_sentinel_dataset_survived_every_teardown_in_this_module`, la
# ÚLTIMA por orden de definición. Es decir: la fila centinela se creaba
# recién AL FINAL del módulo, después de que las historias 1-10 ya habían
# corrido y limpiado sus propios datos — exactamente lo contrario de lo que
# el docstring afirmaba ("creada antes de la primera prueba"). La prueba
# pasaba igual porque la fila existía en el momento en que se consultaba a
# sí misma, no porque hubiera demostrado sobrevivir a nada.
#
# Corrección aplicada: `_sentinel_survives_every_test` es un fixture
# FUNCTION-SCOPED y AUTOUSE=True (se aplica a TODAS las pruebas de este
# módulo sin que cada una tenga que pedirlo explícitamente). Al depender de
# `sentinel_dataset_id` (module-scoped), pytest está OBLIGADO a instanciar
# `sentinel_dataset_id` antes del `setup` de la PRIMERA prueba del módulo —
# sea cual sea su nombre u orden de definición — porque resolver la cadena
# de dependencias de un fixture autouse ocurre antes de ejecutar el cuerpo
# de cualquier prueba. Además, este fixture comprueba la existencia de la
# fila ANTES y DESPUÉS de CADA prueba individual (no solo de la última) y
# registra cada comprobación en `_SENTINEL_AUDIT_LOG`, una bitácora que la
# prueba final inspecciona — la evidencia de supervivencia ya no depende de
# que ninguna prueba concreta se ejecute en un punto particular del orden.


_SENTINEL_AUDIT_LOG: list[tuple[str, str, bool]] = []


async def _sentinel_row_exists(engine, sentinel_id: str) -> bool:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT 1 FROM catalog_datasets WHERE id = :id"), {"id": sentinel_id}
            )
        ).first()
    return row is not None


@pytest.fixture(scope="module")
async def _sentinel_engine():
    """Motor propio de alcance módulo: el fixture `engine` (function-scoped,
    usado por las historias) se dispone al final de cada prueba individual,
    así que no sirve para verificar algo que debe sobrevivir MÁS ALLÁ de una
    sola prueba."""

    database = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
    )
    yield database
    await database.dispose()


@pytest.fixture(scope="module")
async def sentinel_dataset_id(_sentinel_engine):
    """Fila centinela AJENA a cualquier caso de este módulo. NO es autouse
    directamente (ver `_sentinel_survives_every_test` más abajo, que sí lo
    es y fuerza su creación temprana por dependencia transitiva) para poder
    seguir exponiendo el identificador por nombre a quien lo necesite."""

    sentinel_id = f"{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[4:8]}"
    now = datetime.now(UTC)
    factory = async_sessionmaker(_sentinel_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            CatalogDataset(
                id=sentinel_id,
                name="Fila centinela T-611 (ajena a todos los casos, no tocar)",
                publisher="Centinela de Prueba",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                data_updated_at=now,
                api_active=True,
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
    assert await _sentinel_row_exists(_sentinel_engine, sentinel_id), (
        "la fila centinela no quedó creada antes de la primera prueba del módulo"
    )
    try:
        yield sentinel_id
    finally:
        # Comprueba supervivencia ANTES de borrarla ella misma: si algún
        # teardown anterior de la suite ya la hubiera eliminado (regresión
        # real del aislamiento de datos), esta aserción falla aquí, en el
        # teardown final del módulo — el punto exacto donde debe detectarse.
        assert await _sentinel_row_exists(_sentinel_engine, sentinel_id), (
            "la fila centinela desapareció antes del teardown final del módulo: "
            "alguna prueba/teardown de esta suite borró datos ajenos"
        )
        async with _sentinel_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM catalog_datasets WHERE id = :id"), {"id": sentinel_id}
            )
        assert not await _sentinel_row_exists(_sentinel_engine, sentinel_id), (
            "el borrado final de la fila centinela no surtió efecto"
        )


@pytest.fixture(autouse=True)
async def _sentinel_survives_every_test(request, sentinel_dataset_id, _sentinel_engine):
    """AUTOUSE, function-scoped: envuelve TODAS las pruebas de este módulo
    (historias 1-10 y la prueba final) sin que ninguna lo declare
    explícitamente. Depender de `sentinel_dataset_id` fuerza su creación
    antes de la primera prueba (ver bloque de comentarios de arriba).
    Verifica presencia antes y después de CADA prueba y deja constancia en
    `_SENTINEL_AUDIT_LOG` — evidencia mecánica, no basada en el orden de
    ejecución, de que la fila sobrevivió a cada teardown intermedio."""

    exists_before = await _sentinel_row_exists(_sentinel_engine, sentinel_dataset_id)
    _SENTINEL_AUDIT_LOG.append(("before", request.node.name, exists_before))
    assert exists_before, f"la fila centinela ya no existía al iniciar {request.node.name!r}"

    yield

    exists_after = await _sentinel_row_exists(_sentinel_engine, sentinel_dataset_id)
    _SENTINEL_AUDIT_LOG.append(("after", request.node.name, exists_after))
    assert exists_after, f"la fila centinela desapareció durante/después de {request.node.name!r}"


async def test_zz_sentinel_dataset_survived_every_teardown_in_this_module(
    sentinel_dataset_id: str, _sentinel_engine
) -> None:
    """Corrección 1, condición 6 — confirmación final y explícita.

    La garantía real de que la fila centinela existió ANTES de la primera
    historia y sobrevivió a CADA teardown intermedio no depende de que esta
    prueba se ejecute al final por orden alfabético/de definición: la aporta
    `_sentinel_survives_every_test` (autouse, function-scoped, arriba), que
    audita presencia antes y después de cada prueba del módulo — incluidas
    las historias 1-10 — y haría fallar esa prueba concreta (no esta) si la
    fila desapareciera en cualquier punto intermedio. Esta prueba solo
    inspecciona esa bitácora acumulada y añade una comprobación directa
    final contra Postgres."""

    assert _SENTINEL_AUDIT_LOG, "la bitácora de auditoría está vacía: revisar el fixture autouse"
    assert all(existed for _phase, _name, existed in _SENTINEL_AUDIT_LOG), (
        f"la fila centinela desapareció en algún punto de la suite: {_SENTINEL_AUDIT_LOG}"
    )
    audited_test_names = {
        name
        for _phase, name, _existed in _SENTINEL_AUDIT_LOG
        if name != "test_zz_sentinel_dataset_survived_every_teardown_in_this_module"
    }
    assert len(audited_test_names) >= 10, (
        "se esperaban al menos 10 historias auditadas antes de esta prueba "
        f"(1-9 con subcasos + 10), hubo {len(audited_test_names)}: {sorted(audited_test_names)}"
    )
    assert await _sentinel_row_exists(_sentinel_engine, sentinel_dataset_id), (
        "comprobación final directa: la fila centinela debe seguir presente "
        "en este punto (el teardown del propio fixture la borrará después)"
    )
    print(
        f"\n[centinela] id={sentinel_dataset_id} — bitácora con "
        f"{len(_SENTINEL_AUDIT_LOG)} comprobaciones sobre "
        f"{len(audited_test_names)} pruebas previas, todas 'existe=True'; "
        f"primer registro={_SENTINEL_AUDIT_LOG[0]}, "
        f"último registro antes de esta prueba={_SENTINEL_AUDIT_LOG[-1]}"
    )
