"""Orquestacion de una corrida del grafo de juguete (T-300).

Cancelacion cooperativa para DELETE de corrida activa (contracts/api-rest.md
§7b): un `threading.Event` compartido, revisado entre cada paso del grafo y
durante la espera artificial entre pasos. Cancelar el `asyncio.Task` que
envuelve `asyncio.to_thread(...)` NO interrumpe el hilo subyacente (Python no
puede matar un hilo a la fuerza), por eso la senal de parada es este evento
explicito, no `Task.cancel()`.

Todo el ciclo de vida de una corrida (motor SQLAlchemy, checkpointer,
esperas artificiales entre pasos) ocurre dentro de UNA sola llamada
`asyncio.to_thread(..., loop_factory=SelectorEventLoop)` en Windows: un
unico loop para toda la corrida evita el problema de reabrir conexiones
psycopg-async en loops distintos entre pasos.
"""

from __future__ import annotations

import asyncio
import calendar
import dataclasses
import hashlib
import secrets
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.deterministic_dependencies import (
    RuntimeLLMUsage,
    build_real_runtime_dependencies,
)
from app.agent.deterministic_graph import SupervisorBudgets
from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    DeterministicPersistenceCancelled,
    persist_deterministic_execution,
)
from app.agent.deterministic_runtime import (
    DeterministicRunCancelled,
    SynthesisIntegrityError,
    run_deterministic_agent,
)
from app.agent.durability import get_run, touch_run_heartbeat, write_terminal_event_once
from app.agent.graph import (
    ClaimPlannerOutput,
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    build_graph,
    initial_state,
)
from app.agent.persistence import (
    load_allowed_grounded_facts,
    load_dataset_evidence_metadata,
    persist_final_answer,
    persist_run_telemetry,
    record_step_and_event,
    update_step_tool_result,
)
from app.agent.toy_graph import NODES, build_toy_graph
from app.config import Settings
from app.db.engine import create_app_async_engine
from app.db.models import AgentRun
from app.llm.factory import (
    LLMConfigurationError,
    LLMProviderError,
    get_structured_chat_model,
)
from app.quality.claim_labels import build_presentation_warnings, intent_relevance_tokens
from app.quality.grounded_facts import QuantitativeFactKind
from app.quality.grounded_synthesis import (
    GroundedSynthesisValidationError,
    build_grounded_synthesis_fallback,
    render_grounded_synthesis,
    validate_grounded_synthesis_plan,
)
from app.schemas import (
    ErrorDetail,
    ErrorEnvelope,
    TextualFactResponse,
    materialize_textual_fact_fields,
)
from app.tools.buscar_catalogo import buscar_catalogo
from app.tools.ejecutar_soql import ejecutar_soql
from app.tools.explorar_valores import explorar_valores
from app.tools.perfilar_dataset import perfilar_dataset
from app.tools.resolver_geografia import resolver_geografia
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL

DEFAULT_STEP_DELAY_S = 1.0
CANCEL_POLL_INTERVAL_S = 0.2


@dataclass
class ActiveRun:
    task: asyncio.Task
    cancel_event: threading.Event = field(default_factory=threading.Event)


ACTIVE_RUNS: dict[uuid.UUID, ActiveRun] = {}


async def create_run(
    engine: AsyncEngine,
    *,
    worker_instance_id: str,
    question: str,
    retention_user_days: int,
) -> uuid.UUID:
    """Crea la fila `agent_runs` (status=running) para el PoC.

    Genera y descarta un `run_access_token` inmediatamente: las columnas
    `run_access_token_hash`/`run_access_token_expires_at` son NOT NULL en
    data-model.md, pero RF-801 (autorizacion Bearer) queda fuera de alcance
    de T-300 (pertenece a T-304) -- ver decision de alcance del plan.
    """

    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question=question,
                status="running",
                worker_instance_id=worker_instance_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash=token_hash,
                run_access_token_expires_at=now + timedelta(days=retention_user_days),
                retention_class="user",
                created_at=now,
            )
        )
    return run_id


async def create_public_run(
    engine: AsyncEngine,
    *,
    worker_instance_id: str,
    question: str,
    context_hint: str | None,
    retention_user_days: int,
) -> tuple[uuid.UUID, str, datetime]:
    """Crea una corrida publica ``user`` y entrega el token una sola vez.

    RF-801 prohíbe que el JSON público elija ``retention_class``. En vez de
    ampliar ``create_run`` (que conserva el comportamiento deliberado del
    PoC T-300), esta interfaz separada fija ``user``, reutiliza la misma
    generación/hash SHA-256 y devuelve el secreto únicamente al handler que
    responde el 202. Nunca persiste ni registra el valor en claro.
    """

    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(days=retention_user_days)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question=question,
                context_hint=context_hint,
                status="running",
                worker_instance_id=worker_instance_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash=token_hash,
                run_access_token_expires_at=expires_at,
                retention_class="user",
                created_at=now,
            )
        )
    return run_id, token, expires_at


def _add_months(value: datetime, months: int) -> datetime:
    """Suma meses de calendario para la retención de corridas OE3."""

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


async def create_eval_run(
    engine: AsyncEngine,
    *,
    worker_instance_id: str,
    question: str,
    retention_eval_months: int,
) -> uuid.UUID:
    """Crea una corrida interna ``eval``; nunca expone su token (RF-801)."""

    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question=question,
                status="running",
                worker_instance_id=worker_instance_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                run_access_token_expires_at=_add_months(now, retention_eval_months),
                retention_class="eval",
                created_at=now,
            )
        )
    return run_id


def start_toy_run_task(
    sqlalchemy_database_url: str, psycopg_database_url: str, run_id: uuid.UUID, step_delay_s: float
) -> None:
    """Lanza la corrida como tarea cancelable y la registra para DELETE.

    Recibe las DOS formas de la URL (config.py): `sqlalchemy_database_url`
    (`postgresql+psycopg://...`) para el engine SQLAlchemy y
    `psycopg_database_url` (`postgresql://...` sin prefijo) para
    `AsyncPostgresSaver.from_conn_string`, igual que `db/checkpointer.py`.
    """

    cancel_event = threading.Event()
    task = asyncio.create_task(
        _execute_toy_run(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        )
    )
    ACTIVE_RUNS[run_id] = ActiveRun(task=task, cancel_event=cancel_event)
    task.add_done_callback(lambda _task: ACTIVE_RUNS.pop(run_id, None))


def start_run_task(settings: Settings, run_id: uuid.UUID) -> None:
    """Lanza el grafo real T-303 como tarea cancelable (T-304 lo expondrá)."""

    cancel_event = threading.Event()
    task = asyncio.create_task(_execute_agent_run(settings, run_id, cancel_event))
    ACTIVE_RUNS[run_id] = ActiveRun(task=task, cancel_event=cancel_event)
    task.add_done_callback(lambda _task: ACTIVE_RUNS.pop(run_id, None))


async def request_cancel_and_wait(run_id: uuid.UUID, grace_s: float) -> None:
    """DELETE de corrida activa (api-rest.md §7b): pide parada cooperativa y
    espera un plazo corto; si no coopera a tiempo, el llamador continua con
    el borrado de todos modos (la tarea puede seguir corriendo en segundo
    plano y sus escrituras posteriores fallaran silenciosamente porque la
    fila ya no existira)."""

    active = ACTIVE_RUNS.get(run_id)
    if active is None:
        return
    active.cancel_event.set()
    try:
        await asyncio.wait_for(asyncio.shield(active.task), timeout=grace_s)
    except TimeoutError:
        pass


async def _execute_toy_run(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_with_selector,
            sqlalchemy_database_url,
            psycopg_database_url,
            run_id,
            step_delay_s,
            cancel_event,
        )
    else:
        await _execute_toy_run_async(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        )


async def _execute_agent_run(
    settings: Settings, run_id: uuid.UUID, cancel_event: threading.Event
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(_run_agent_with_selector, settings, run_id, cancel_event)
    else:
        await execute_agent_run_async(settings, run_id, cancel_event)


def _run_agent_with_selector(
    settings: Settings, run_id: uuid.UUID, cancel_event: threading.Event
) -> None:
    asyncio.run(
        execute_agent_run_async(settings, run_id, cancel_event),
        loop_factory=asyncio.SelectorEventLoop,
    )


def _secret_value(secret) -> str | None:
    return secret.get_secret_value() if secret else None


def _structured_model(settings: Settings, schema):
    return get_structured_chat_model(
        settings.llm_provider,
        settings.llm_model,
        schema,
        google_api_key=_secret_value(settings.google_api_key),
        anthropic_api_key=_secret_value(settings.anthropic_api_key),
        include_raw=True,
        temperature=0,
        timeout=30,
        max_retries=1,
    )


def _usage_totals(state: dict) -> tuple[int, int, float]:
    usages = state.get("usage", [])
    return (
        sum(int(item.get("input_tokens", 0)) for item in usages),
        sum(int(item.get("output_tokens", 0)) for item in usages),
        round(sum(float(item.get("estimated_cost_usd", 0)) for item in usages), 6),
    )


async def execute_deterministic_agent_run_async(
    settings: Settings,
    run_id: uuid.UUID,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Ejecuta el runtime v2; nunca cae automáticamente al grafo legado."""

    cancel_event = cancel_event or threading.Event()
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    started = time.monotonic()
    llm_usage = RuntimeLLMUsage()
    observed_steps = 0
    try:
        run = await get_run(engine, run_id)
        if run is None:
            raise LookupError(f"run_id={run_id} no existe")
        if settings.embedding_model is None:
            raise LLMConfigurationError("EMBEDDING_MODEL es obligatorio para buscar catálogo")
        embedding_client = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=_secret_value(settings.google_api_key),
        )
        async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
            retrieved_dataset_ids: list[str] = []
            attempted_dataset_ids: list[str] = []

            async def observe_transition(entry, usage) -> None:
                nonlocal observed_steps
                observed_steps += 1
                dataset_id = (
                    retrieved_dataset_ids[entry.candidate_index]
                    if entry.candidate_index is not None
                    and entry.candidate_index < len(retrieved_dataset_ids)
                    else None
                )
                if entry.node.value == "select_candidate" and dataset_id:
                    attempted_dataset_ids.append(dataset_id)
                await record_step_and_event(
                    engine,
                    run_id,
                    step_number=observed_steps,
                    node=entry.node.value,
                    display_message=entry.reason,
                    detail={
                        "runtime": "deterministic",
                        "candidate_index": entry.candidate_index,
                        "dataset_id": dataset_id,
                        "retrieved_dataset_ids": list(retrieved_dataset_ids),
                        "attempted_dataset_ids": list(dict.fromkeys(attempted_dataset_ids)),
                        "plan_validation_errors": (
                            [entry.diagnostic_code] if entry.diagnostic_code else []
                        ),
                        "usage": usage.model_dump(mode="json"),
                    },
                )
                await touch_run_heartbeat(engine, run_id)

            dependencies = build_real_runtime_dependencies(
                settings=settings,
                engine=engine,
                http_client=http_client,
                embedding_client=embedding_client,
                usage=llm_usage,
                is_cancelled=cancel_event.is_set,
            )
            original_retrieve = dependencies.retrieve

            async def retrieve_with_diagnostics(intent):
                retrieval = await original_retrieve(intent)
                retrieved_dataset_ids.extend(
                    candidate.item.dataset_id for candidate in retrieval.candidates
                )
                return retrieval

            dependencies = dataclasses.replace(dependencies, retrieve=retrieve_with_diagnostics)
            original_execute = dependencies.execute

            async def execute_with_observability(validated):
                tool_started = time.monotonic()
                tool_input = {
                    "dataset_id": validated.dataset_id,
                    "plan_hash": validated.source_plan_hash,
                }
                try:
                    execution = await original_execute(validated)
                except DeterministicExecutionError as exc:
                    await update_step_tool_result(
                        engine,
                        run_id,
                        step_number=observed_steps,
                        tool_input=tool_input,
                        tool_output=exc.tool_output or {},
                        latency_ms=round((time.monotonic() - tool_started) * 1000),
                        error=str(exc),
                    )
                    raise
                await update_step_tool_result(
                    engine,
                    run_id,
                    step_number=observed_steps,
                    tool_input=tool_input,
                    tool_output=execution.tool_output,
                    latency_ms=round((time.monotonic() - tool_started) * 1000),
                )
                return execution

            dependencies = dataclasses.replace(dependencies, execute=execute_with_observability)
            result = await run_deterministic_agent(
                run.question,
                dependencies=dependencies,
                budgets=SupervisorBudgets(
                    max_candidates=8,
                    max_explorations=6,
                    max_queries=6,
                    max_plan_repairs=2,
                    max_llm_calls=10,
                    max_duration_ms=settings.run_max_duration_s * 1000,
                ),
                is_cancelled=cancel_event.is_set,
                observe_transition=observe_transition,
                defer_synthesis_until_persisted=(settings.deterministic_textual_facts_enabled),
            )
        await touch_run_heartbeat(engine, run_id)
        latency_ms = round((time.monotonic() - started) * 1000)
        evidence: list[dict] = []
        claims: list[dict] = []
        presentation_warnings: list[dict] = []
        persisted = None
        has_internal_textual_result = result.execution is not None and bool(
            getattr(result.execution, "textual_facts", ())
            or getattr(result.execution, "textual_rejections", ())
        )
        if result.status in {"completed", "ready_for_synthesis"} or has_internal_textual_result:
            assert result.execution is not None
            if result.status == "completed" and not settings.deterministic_textual_facts_enabled:
                assert result.synthesis is not None
            if cancel_event.is_set():
                raise DeterministicRunCancelled("corrida cancelada antes de persistir")
            metadata = await load_dataset_evidence_metadata(
                engine,
                result.execution.rendered_query.dataset_id,
            )
            if metadata is None:
                raise LookupError("el dataset ejecutado desapareció antes de persistir")
            persisted = await persist_deterministic_execution(
                result.execution,
                engine=engine,
                run_id=run_id,
                official_publisher_id=metadata.official_publisher_id,
                is_cancelled=cancel_event.is_set,
            )
        if cancel_event.is_set():
            raise DeterministicRunCancelled("corrida cancelada antes del terminal")
        allowed_grounded_facts = None
        synthesis_answer: str | None = None
        if (
            settings.deterministic_textual_facts_enabled
            and persisted is not None
            and result.execution is not None
        ):
            allowed_grounded_facts = await load_allowed_grounded_facts(engine, run_id)
            if allowed_grounded_facts.facts:
                synthesis_plan_attempted = False
                try:
                    if dependencies.plan_synthesis is None:
                        raise GroundedSynthesisValidationError(
                            "no existe planificador de síntesis cerrada"
                        )
                    synthesis_plan_attempted = True
                    synthesis_plan = await dependencies.plan_synthesis(
                        result.intent,
                        allowed_grounded_facts,
                    )
                    validate_grounded_synthesis_plan(
                        synthesis_plan,
                        allowed_grounded_facts,
                    )
                except (
                    GroundedSynthesisValidationError,
                    LLMProviderError,
                    TypeError,
                    ValidationError,
                    ValueError,
                ):
                    synthesis_plan = build_grounded_synthesis_fallback(
                        allowed_grounded_facts,
                        requested_tokens=intent_relevance_tokens(
                            result.intent.topic, result.intent.administrative_terms
                        ),
                    )
                if cancel_event.is_set():
                    raise DeterministicRunCancelled(
                        "corrida cancelada después de planificar síntesis"
                    )
                synthesis_answer = render_grounded_synthesis(
                    synthesis_plan,
                    allowed_grounded_facts,
                )
                synthesis_usage = result.usage.model_copy(
                    update={"llm_calls": (result.usage.llm_calls + int(synthesis_plan_attempted))}
                )
                observed_steps += 1
                await record_step_and_event(
                    engine,
                    run_id,
                    step_number=observed_steps,
                    node="synthesize",
                    display_message=("síntesis literal validada desde hechos persistidos"),
                    detail={
                        "runtime": "deterministic",
                        "schema_version": synthesis_plan.schema_version.value,
                        "allowed_fact_count": len(allowed_grounded_facts.facts),
                        "grounded_synthesis_plan": synthesis_plan.model_dump(mode="json"),
                        "usage": synthesis_usage.model_dump(mode="json"),
                    },
                )
        quantitative_completed = result.status == "completed"
        prepared_textual_count = (
            len(result.execution.textual_facts) if result.execution is not None else 0
        )
        allowed_identities = (
            {(fact.fact_kind.value, fact.id) for fact in allowed_grounded_facts.facts}
            if allowed_grounded_facts is not None
            else set()
        )
        persisted_textual_facts = (
            tuple(
                fact
                for fact in persisted.textual_facts
                if ("textual", fact.fact_id) in allowed_identities
            )
            if settings.deterministic_textual_facts_enabled and persisted is not None
            else ()
        )
        textual_persistence_complete = (
            prepared_textual_count == 0 or len(persisted_textual_facts) == prepared_textual_count
        )
        textual_facts = [
            TextualFactResponse.model_validate(fact.model_dump()).model_dump(mode="json")
            for fact in persisted_textual_facts
        ]
        if settings.deterministic_textual_facts_enabled:
            public_completed = synthesis_answer is not None
            quantitative_completed = any(
                fact.fact_kind is QuantitativeFactKind.QUANTITATIVE
                for fact in (
                    allowed_grounded_facts.facts if allowed_grounded_facts is not None else ()
                )
            )
        else:
            public_completed = quantitative_completed or (
                bool(textual_facts) and textual_persistence_complete
            )
        if public_completed:
            assert persisted is not None
            evidence = [persisted.evidence]
            if quantitative_completed:
                claims = (
                    [
                        claim
                        for claim in persisted.claims
                        if (
                            "quantitative",
                            uuid.UUID(str(claim["claim_id"])),
                        )
                        in allowed_identities
                    ]
                    if settings.deterministic_textual_facts_enabled
                    else list(persisted.claims)
                )
                # RF-212 (contracts/api-rest.md §4c): advertencia de
                # presentación por claim con etiquetado ambiguo, distinta de
                # evidence[].quality.warnings_user. Vacía si no hay ninguna;
                # nunca convierte por sí sola `completed` en `no_evidence`.
                presentation_warnings = build_presentation_warnings(claims)

        final_answer = {
            "run_id": str(run_id),
            "status": "completed" if public_completed else "no_evidence",
            "intention": result.intent.model_dump(mode="json"),
            "summary": (
                synthesis_answer
                if public_completed
                and quantitative_completed
                and settings.deterministic_textual_facts_enabled
                else result.synthesis.answer
                if public_completed and quantitative_completed and result.synthesis is not None
                else (
                    "Se encontraron hechos textuales verificables."
                    if textual_facts
                    else "No encontré evidencia elegible suficiente para responder."
                )
            ),
            "narrative": (
                synthesis_answer
                if public_completed and settings.deterministic_textual_facts_enabled
                else result.synthesis.answer
                if public_completed and quantitative_completed and result.synthesis is not None
                else None
            ),
            "evidence": evidence,
            "claims": claims,
            "presentation_warnings": presentation_warnings,
            "textual_facts": textual_facts,
            "partial_textual_facts": [],
            "no_evidence_report": (
                None
                if public_completed
                else {
                    "reason": result.stop_reason.value if result.stop_reason else "NO_EVIDENCE",
                    "suggestions": [
                        "Reformular la pregunta con tema, territorio o periodo explícitos."
                    ],
                    "datasets_reviewed": [],
                    "external_sources": [],
                }
            ),
            "usage": {
                "steps_used": observed_steps,
                "input_tokens": llm_usage.input_tokens,
                "output_tokens": llm_usage.output_tokens,
                "estimated_cost_usd": llm_usage.estimated_cost_usd,
                "latency_ms": latency_ms,
                "termination_reason": (
                    result.stop_reason.value if result.stop_reason is not None else None
                ),
            },
        }
        await persist_final_answer(
            engine,
            run_id,
            final_answer,
            latency_ms=latency_ms,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            input_tokens=llm_usage.input_tokens,
            output_tokens=llm_usage.output_tokens,
            estimated_cost_usd=llm_usage.estimated_cost_usd,
        )
        await write_terminal_event_once(
            engine,
            run_id,
            status=final_answer["status"],
            error_code=None,
            payload=final_answer,
        )
        return {"final_answer": final_answer, "runtime": "deterministic"}
    except (DeterministicRunCancelled, DeterministicPersistenceCancelled):
        return {}
    except SynthesisIntegrityError as exc:
        latency_ms = round((time.monotonic() - started) * 1000)
        await persist_run_telemetry(
            engine,
            run_id,
            steps_used=observed_steps,
            latency_ms=latency_ms,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            input_tokens=llm_usage.input_tokens,
            output_tokens=llm_usage.output_tokens,
            estimated_cost_usd=llm_usage.estimated_cost_usd,
        )
        payload = ErrorEnvelope(
            error=ErrorDetail(
                code="STRUCTURED_OUTPUT_INVALID",
                status="failed",
                message_user=(
                    "No fue posible producir una respuesta sin cifras "
                    "no respaldadas por la evidencia."
                ),
                message_dev=str(exc),
                retryable=False,
            )
        ).model_dump()
        await write_terminal_event_once(
            engine,
            run_id,
            status="failed",
            error_code="STRUCTURED_OUTPUT_INVALID",
            payload=payload,
        )
        return {"terminal_error": payload, "runtime": "deterministic"}
    except (LLMProviderError, LLMConfigurationError) as exc:
        payload = ErrorEnvelope(
            error=ErrorDetail(
                code="LLM_PROVIDER_ERROR",
                status="failed",
                message_user="El servicio de inteligencia artificial no está disponible.",
                message_dev=str(exc),
                retryable=False,
            )
        ).model_dump()
        await write_terminal_event_once(
            engine,
            run_id,
            status="failed",
            error_code="LLM_PROVIDER_ERROR",
            payload=payload,
        )
        return {"terminal_error": payload, "runtime": "deterministic"}
    except Exception as exc:
        payload = ErrorEnvelope(
            error=ErrorDetail(
                code="INTERNAL",
                status="failed",
                message_user="Ocurrió un error inesperado durante la investigación.",
                message_dev=str(exc),
                retryable=False,
            )
        ).model_dump()
        await write_terminal_event_once(
            engine,
            run_id,
            status="failed",
            error_code="INTERNAL",
            payload=payload,
        )
        return {"terminal_error": payload, "runtime": "deterministic"}
    finally:
        await engine.dispose()


async def execute_agent_run_async(
    settings: Settings,
    run_id: uuid.UUID,
    cancel_event: threading.Event | None = None,
) -> dict:
    if settings.agent_runtime == "legacy":
        return await execute_legacy_agent_run_async(settings, run_id, cancel_event)
    return await execute_deterministic_agent_run_async(settings, run_id, cancel_event)


async def execute_legacy_agent_run_async(
    settings: Settings,
    run_id: uuid.UUID,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Ejecuta el grafo real nodo a nodo y escribe un único terminal."""

    cancel_event = cancel_event or threading.Event()
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    started = time.monotonic()
    try:
        run = await get_run(engine, run_id)
        if run is None:
            raise LookupError(f"run_id={run_id} no existe")
        if settings.embedding_model is None:
            raise LLMConfigurationError("EMBEDDING_MODEL es obligatorio para buscar_catalogo")
        embedding_client = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=_secret_value(settings.google_api_key),
        )
        async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
            app_token = _secret_value(settings.socrata_app_token)

            async def call_buscar(raw_input):
                return await buscar_catalogo(
                    raw_input, engine=engine, embedding_client=embedding_client
                )

            async def call_perfilar(raw_input):
                return await perfilar_dataset(
                    raw_input,
                    engine=engine,
                    http_client=http_client,
                    app_token=app_token,
                )

            async def call_geografia(raw_input):
                return await resolver_geografia(raw_input, engine=engine)

            async def call_explorar(raw_input):
                return await explorar_valores(
                    raw_input, engine=engine, http_client=http_client, app_token=app_token
                )

            async def call_soql(raw_input):
                return await ejecutar_soql(
                    raw_input,
                    engine=engine,
                    http_client=http_client,
                    app_token=app_token,
                )

            deps = GraphDependencies(
                engine=engine,
                planner_model=_structured_model(settings, PlannerOutput),
                router_model=_structured_model(settings, RouterOutput),
                synthesizer_model=_structured_model(settings, SynthesisOutput),
                claim_model=_structured_model(settings, ClaimPlannerOutput),
                tools={
                    "buscar_catalogo": call_buscar,
                    "perfilar_dataset": call_perfilar,
                    "resolver_geografia": call_geografia,
                    "explorar_valores": call_explorar,
                    "ejecutar_soql": call_soql,
                },
                llm_provider=settings.llm_provider,
                llm_model=settings.llm_model,
                max_steps=settings.agent_max_steps,
                placeholder_min_ratio=settings.placeholder_min_ratio,
            )
            config = {"configurable": {"thread_id": str(run_id)}}
            state: dict | None = initial_state(
                run_id,
                run.question,
                max_steps=settings.agent_max_steps,
                context_hint=run.context_hint,
            )
            async with AsyncPostgresSaver.from_conn_string(settings.psycopg_database_url) as saver:
                await saver.setup()
                graph = build_graph(deps, saver, interrupt=True)
                while True:
                    if cancel_event.is_set():
                        return {}
                    state = await graph.ainvoke(state, config, durability="sync")
                    await touch_run_heartbeat(engine, run_id)
                    snapshot = await graph.aget_state(config)
                    if not snapshot.next:
                        break
                    state = None

        assert state is not None
        latency_ms = round((time.monotonic() - started) * 1000)
        if state.get("terminal_error"):
            error = state["terminal_error"]
            await write_terminal_event_once(
                engine,
                run_id,
                status="failed",
                error_code=error["error"]["code"],
                payload=error,
            )
            return state
        final_answer = materialize_textual_fact_fields(state["final_answer"])
        state["final_answer"] = final_answer
        input_tokens, output_tokens, estimated_cost = _usage_totals(state)
        final_answer["usage"]["latency_ms"] = latency_ms
        final_answer["usage"]["estimated_cost_usd"] = estimated_cost
        await persist_final_answer(
            engine,
            run_id,
            final_answer,
            latency_ms=latency_ms,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
        )
        await write_terminal_event_once(
            engine,
            run_id,
            status=final_answer["status"],
            error_code=None,
            payload=final_answer,
        )
        return state
    except (LLMProviderError, LLMConfigurationError) as exc:
        payload = ErrorEnvelope(
            error=ErrorDetail(
                code="LLM_PROVIDER_ERROR",
                status="failed",
                message_user=(
                    "El servicio de inteligencia artificial no está disponible en este momento."
                ),
                message_dev=str(exc),
                retryable=False,
            )
        ).model_dump()
        await write_terminal_event_once(
            engine,
            run_id,
            status="failed",
            error_code="LLM_PROVIDER_ERROR",
            payload=payload,
        )
        return {"terminal_error": payload}
    except Exception as exc:
        payload = ErrorEnvelope(
            error=ErrorDetail(
                code="INTERNAL",
                status="failed",
                message_user="Ocurrió un error inesperado durante la investigación.",
                message_dev=str(exc),
                retryable=False,
            )
        ).model_dump()
        try:
            await write_terminal_event_once(
                engine,
                run_id,
                status="failed",
                error_code="INTERNAL",
                payload=payload,
            )
        except Exception:
            pass
        return {"terminal_error": payload}
    finally:
        await engine.dispose()


def _run_with_selector(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    asyncio.run(
        _execute_toy_run_async(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _execute_toy_run_async(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    engine = create_app_async_engine(sqlalchemy_database_url, pool_pre_ping=True)
    try:
        config = {"configurable": {"thread_id": str(run_id)}}
        state = {"run_id": str(run_id), "steps_done": []}
        async with AsyncPostgresSaver.from_conn_string(psycopg_database_url) as saver:
            graph = build_toy_graph(engine, run_id, saver)
            for index in range(len(NODES)):
                if await _sleep_cancelable(step_delay_s, cancel_event):
                    return
                state = await graph.ainvoke(
                    state if index == 0 else None, config, durability="sync"
                )
                await touch_run_heartbeat(engine, run_id)
        await write_terminal_event_once(
            engine,
            run_id,
            status="completed",
            error_code=None,
            payload={
                "run_id": str(run_id),
                "status": "completed",
                "summary": (
                    "Demostracion T-300 completada: los "
                    f"{len(NODES)} pasos del grafo de juguete se ejecutaron."
                ),
                "usage": {"steps_used": len(NODES)},
            },
        )
    except Exception as exc:
        try:
            await write_terminal_event_once(
                engine,
                run_id,
                status="failed",
                error_code="INTERNAL",
                payload=ErrorEnvelope(
                    error=ErrorDetail(
                        code="INTERNAL",
                        status="failed",
                        message_user="Ocurrio un error inesperado en la demostracion.",
                        message_dev=str(exc),
                        retryable=False,
                    )
                ).model_dump(),
            )
        except Exception:
            pass
    finally:
        await engine.dispose()


async def _sleep_cancelable(total_s: float, cancel_event: threading.Event) -> bool:
    """Duerme en incrementos cortos para responder rapido a `cancel_event`.

    Devuelve True si debe abortarse (cancelado durante o antes de la espera).
    """

    remaining = total_s
    while remaining > 0:
        if cancel_event.is_set():
            return True
        step = min(CANCEL_POLL_INTERVAL_S, remaining)
        await asyncio.sleep(step)
        remaining -= step
    return cancel_event.is_set()
