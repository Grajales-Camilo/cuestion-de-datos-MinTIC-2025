import asyncio
import contextlib
import hmac
import json
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, Field
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent import durability, heartbeat_sweep, runner, worker_lease
from app.catalog.search import CatalogSearchSummary, search_catalog
from app.config import get_settings
from app.db.checkpointer import setup_checkpointer
from app.db.engine import create_app_async_engine
from app.db.models import AgentRun
from app.db.publishers import (
    DEFAULT_FIXTURE_PATH,
    OfficialPublishersFixture,
    ReloadSummary,
    load_fixture,
    reload_official_publishers,
)
from app.schemas import (
    CatalogIndexCheck,
    CatalogSearchResponse,
    CatalogSearchResult,
    ErrorDetail,
    ErrorEnvelope,
    HealthResponse,
    LLMProviderCheck,
    PublishersReloadSummary,
)

POC_SWEEP_INTERVAL_S = 2.0
POC_LEASE_RENEWAL_MIN_INTERVAL_S = 1.0
POC_SSE_POLL_INTERVAL_S = 0.3
POC_SSE_PING_INTERVAL_S = 15.0

APP_VERSION = "2.0.0"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    await setup_checkpointer(settings)

    worker_instance_id, _closed_on_startup = await _startup_worker_lifecycle_with_platform_loop(
        settings.sqlalchemy_database_url, settings.worker_lease_ttl_s
    )
    app.state.worker_instance_id = worker_instance_id

    background_tasks = [
        asyncio.create_task(
            _lease_renewal_loop(
                settings.sqlalchemy_database_url, worker_instance_id, settings.worker_lease_ttl_s
            )
        ),
        asyncio.create_task(
            _heartbeat_sweep_loop(
                settings.sqlalchemy_database_url,
                worker_instance_id,
                settings.run_heartbeat_timeout_s,
                settings.run_max_duration_s,
            )
        ),
    ]
    app.state.background_tasks = background_tasks

    yield

    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await _mark_worker_shutdown_with_platform_loop(
        settings.sqlalchemy_database_url, worker_instance_id
    )


async def _startup_worker_lifecycle_with_platform_loop(
    database_url: str, lease_ttl_s: int
) -> tuple[str, int]:
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_startup_worker_lifecycle_with_selector, database_url, lease_ttl_s
        )
    return await _startup_worker_lifecycle_async(database_url, lease_ttl_s)


def _run_startup_worker_lifecycle_with_selector(
    database_url: str, lease_ttl_s: int
) -> tuple[str, int]:
    return asyncio.run(
        _startup_worker_lifecycle_async(database_url, lease_ttl_s),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _startup_worker_lifecycle_async(database_url: str, lease_ttl_s: int) -> tuple[str, int]:
    """Registra la instancia y cierra huerfanas de instancias con lease vencida
    (arranque idempotente, plan.md §11), en una sola conexion."""

    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        worker_instance_id = await worker_lease.register_worker_instance(engine, lease_ttl_s)
        closed = await worker_lease.close_stale_running_runs(engine, worker_instance_id)
        return worker_instance_id, closed
    finally:
        await engine.dispose()


async def _renew_lease_with_platform_loop(
    database_url: str, worker_instance_id: str, ttl_s: int
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_renew_lease_with_selector, database_url, worker_instance_id, ttl_s
        )
    else:
        await _renew_lease_async(database_url, worker_instance_id, ttl_s)


def _run_renew_lease_with_selector(database_url: str, worker_instance_id: str, ttl_s: int) -> None:
    asyncio.run(
        _renew_lease_async(database_url, worker_instance_id, ttl_s),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _renew_lease_async(database_url: str, worker_instance_id: str, ttl_s: int) -> None:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        await worker_lease.renew_lease(engine, worker_instance_id, ttl_s)
    finally:
        await engine.dispose()


async def _mark_worker_shutdown_with_platform_loop(
    database_url: str, worker_instance_id: str
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(_run_mark_shutdown_with_selector, database_url, worker_instance_id)
    else:
        await _mark_worker_shutdown_async(database_url, worker_instance_id)


def _run_mark_shutdown_with_selector(database_url: str, worker_instance_id: str) -> None:
    asyncio.run(
        _mark_worker_shutdown_async(database_url, worker_instance_id),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _mark_worker_shutdown_async(database_url: str, worker_instance_id: str) -> None:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        await worker_lease.mark_worker_shutdown(engine, worker_instance_id)
    finally:
        await engine.dispose()


async def _sweep_with_platform_loop(
    database_url: str, worker_instance_id: str, heartbeat_timeout_s: int, max_duration_s: int
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_sweep_with_selector,
            database_url,
            worker_instance_id,
            heartbeat_timeout_s,
            max_duration_s,
        )
    else:
        await _sweep_async(database_url, worker_instance_id, heartbeat_timeout_s, max_duration_s)


def _run_sweep_with_selector(
    database_url: str, worker_instance_id: str, heartbeat_timeout_s: int, max_duration_s: int
) -> None:
    asyncio.run(
        _sweep_async(database_url, worker_instance_id, heartbeat_timeout_s, max_duration_s),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _sweep_async(
    database_url: str, worker_instance_id: str, heartbeat_timeout_s: int, max_duration_s: int
) -> None:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        await heartbeat_sweep.sweep_orphaned_runs(
            engine,
            own_worker_instance_id=worker_instance_id,
            heartbeat_timeout_s=heartbeat_timeout_s,
            max_duration_s=max_duration_s,
        )
    finally:
        await engine.dispose()


async def _lease_renewal_loop(database_url: str, worker_instance_id: str, ttl_s: int) -> None:
    """Renueva heartbeat/lease cada tercio del TTL (plan.md §11)."""

    interval = max(ttl_s / 3, POC_LEASE_RENEWAL_MIN_INTERVAL_S)
    while True:
        await asyncio.sleep(interval)
        await _renew_lease_with_platform_loop(database_url, worker_instance_id, ttl_s)


async def _heartbeat_sweep_loop(
    database_url: str, worker_instance_id: str, heartbeat_timeout_s: int, max_duration_s: int
) -> None:
    while True:
        await asyncio.sleep(POC_SWEEP_INTERVAL_S)
        await _sweep_with_platform_loop(
            database_url, worker_instance_id, heartbeat_timeout_s, max_duration_s
        )


app = FastAPI(title="Cuestion de Datos API", version=APP_VERSION, lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-Admin-Token"],
)


class ApiError(Exception):
    """Error que se serializa con el sobre estandar (contracts/api-rest.md §6)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message_user: str,
        *,
        message_dev: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.status_code = status_code
        self.envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=code, message_user=message_user, message_dev=message_dev, retryable=retryable
            )
        )


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content=exc.envelope.model_dump(exclude_none=True)
    )


def require_admin_token(
    request: Request, x_admin_token: Annotated[str | None, Header()] = None
) -> None:
    settings = request.app.state.settings
    admin_token = getattr(settings, "admin_token", None)
    expected = admin_token.get_secret_value() if admin_token else None
    if not expected or not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "No autorizado. Verifica el token de administracion.",
            message_dev="X-Admin-Token ausente o invalido.",
        )


@app.get("/v2/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(response: Response) -> HealthResponse:
    """RF-702: health con HealthResponse en 200 y 503."""

    settings = app.state.settings
    checks: dict[str, object] = {}

    database_ok, catalog_index = await check_database_and_catalog(settings.sqlalchemy_database_url)

    checks["database"] = "ok" if database_ok else "degraded"
    checks["catalog_index"] = catalog_index
    checks["llm_provider"] = LLMProviderCheck(
        status="ok" if settings.llm_provider_configured else "degraded",
        provider=settings.llm_provider,
        model=settings.llm_model,
        detail=None if settings.llm_provider_configured else "not_configured",
    )

    global_status = (
        "ok"
        if checks["database"] == "ok"
        and catalog_index.status == "ok"
        and checks["llm_provider"].status == "ok"  # type: ignore[union-attr]
        else "degraded"
    )
    if global_status == "degraded":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(status=global_status, checks=checks, version=APP_VERSION)


async def check_database_and_catalog(database_url: str) -> tuple[bool, CatalogIndexCheck]:
    if sys.platform == "win32":
        return await asyncio.to_thread(_run_catalog_check_with_selector, database_url)
    return await _check_database_and_catalog_async(database_url)


def _run_catalog_check_with_selector(database_url: str) -> tuple[bool, CatalogIndexCheck]:
    return asyncio.run(
        _check_database_and_catalog_async(database_url),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _check_database_and_catalog_async(database_url: str) -> tuple[bool, CatalogIndexCheck]:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    catalog_index = CatalogIndexCheck(status="degraded", detail="not_initialized")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            result = await connection.execute(
                text("SELECT to_regclass('public.catalog_embeddings') IS NOT NULL")
            )
            catalog_table_exists = bool(result.scalar_one())
            if catalog_table_exists:
                count_result = await connection.execute(
                    text("SELECT count(*) FROM catalog_embeddings")
                )
                datasets_indexed = int(count_result.scalar_one())
                if datasets_indexed > 0:
                    catalog_index = CatalogIndexCheck(
                        status="ok",
                        datasets_indexed=datasets_indexed,
                    )
                else:
                    catalog_index = CatalogIndexCheck(
                        status="degraded",
                        datasets_indexed=0,
                        detail="not_initialized",
                    )
            return True, catalog_index
    except Exception:
        return False, catalog_index
    finally:
        await engine.dispose()


@app.post(
    "/v2/admin/publishers/reload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PublishersReloadSummary,
    dependencies=[Depends(require_admin_token)],
)
async def reload_publishers(request: Request) -> PublishersReloadSummary:
    """T-106/RF-401: recarga el fixture versionado de publicadores oficiales y aliases."""

    settings = request.app.state.settings
    fixture = load_fixture(DEFAULT_FIXTURE_PATH)
    summary = await _reload_publishers_with_platform_loop(settings.sqlalchemy_database_url, fixture)
    return PublishersReloadSummary(
        publishers_created=summary.publishers_created,
        publishers_updated=summary.publishers_updated,
        aliases_created=summary.aliases_created,
        ambiguous_aliases=summary.ambiguous_aliases,
    )


async def _reload_publishers_with_platform_loop(
    database_url: str, fixture: OfficialPublishersFixture
) -> ReloadSummary:
    if sys.platform == "win32":
        return await asyncio.to_thread(_run_reload_publishers_with_selector, database_url, fixture)
    return await _reload_publishers_async(database_url, fixture)


def _run_reload_publishers_with_selector(
    database_url: str, fixture: OfficialPublishersFixture
) -> ReloadSummary:
    return asyncio.run(
        _reload_publishers_async(database_url, fixture),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _reload_publishers_async(
    database_url: str, fixture: OfficialPublishersFixture
) -> ReloadSummary:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        return await reload_official_publishers(engine, fixture)
    finally:
        await engine.dispose()


@app.get("/v2/catalog/search", response_model=CatalogSearchResponse)
async def catalog_search(
    request: Request,
    q: str,
    k: int = 10,
) -> CatalogSearchResponse:
    """T-204/RF-302: busqueda semantica directa sobre catalog_embeddings existente."""

    query = q.strip()
    if len(query) < 3 or len(query) > 500:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "La consulta debe tener entre 3 y 500 caracteres.",
            message_dev="q debe tener entre 3 y 500 caracteres despues de trim.",
        )
    if k < 1 or k > 25:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "k debe estar entre 1 y 25.",
            message_dev="k debe estar entre 1 y 25; no se recorta silenciosamente.",
        )

    settings = request.app.state.settings
    if settings.google_api_key is None or not settings.google_api_key.get_secret_value():
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_PROVIDER_ERROR",
            "El proveedor de embeddings no esta configurado.",
            message_dev="GOOGLE_API_KEY ausente para embeber la consulta del catalogo.",
            retryable=False,
        )
    if settings.embedding_model is None:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_PROVIDER_ERROR",
            "El modelo de embeddings no esta configurado.",
            message_dev="EMBEDDING_MODEL ausente para busqueda de catalogo.",
            retryable=False,
        )

    try:
        summary = await catalog_search_with_platform_loop(
            database_url=settings.sqlalchemy_database_url,
            google_api_key=settings.google_api_key,
            embedding_model=settings.embedding_model,
            query=query,
            k=k,
            stale_after_days=settings.catalog_stale_after_days,
        )
    except ValueError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "La busqueda de catalogo no cumple el contrato.",
            message_dev=str(exc),
        ) from exc

    return catalog_search_response_from_summary(summary)


async def catalog_search_with_platform_loop(
    *,
    database_url: str,
    google_api_key,
    embedding_model: str,
    query: str,
    k: int,
    stale_after_days: int,
) -> CatalogSearchSummary:
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_catalog_search_with_selector,
            database_url,
            google_api_key,
            embedding_model,
            query,
            k,
            stale_after_days,
        )
    return await _catalog_search_async(
        database_url=database_url,
        google_api_key=google_api_key,
        embedding_model=embedding_model,
        query=query,
        k=k,
        stale_after_days=stale_after_days,
    )


def _run_catalog_search_with_selector(
    database_url: str,
    google_api_key,
    embedding_model: str,
    query: str,
    k: int,
    stale_after_days: int,
) -> CatalogSearchSummary:
    return asyncio.run(
        _catalog_search_async(
            database_url=database_url,
            google_api_key=google_api_key,
            embedding_model=embedding_model,
            query=query,
            k=k,
            stale_after_days=stale_after_days,
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _catalog_search_async(
    *,
    database_url: str,
    google_api_key,
    embedding_model: str,
    query: str,
    k: int,
    stale_after_days: int,
) -> CatalogSearchSummary:
    embedding_client = GoogleGenerativeAIEmbeddings(
        model=embedding_model,
        google_api_key=google_api_key,
    )
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        return await search_catalog(
            engine,
            embedding_client=embedding_client,
            query=query,
            k=k,
            stale_after_days=stale_after_days,
            model=embedding_model,
        )
    finally:
        await engine.dispose()


def catalog_search_response_from_summary(summary: CatalogSearchSummary) -> CatalogSearchResponse:
    return CatalogSearchResponse(
        query=summary.query,
        results=[
            CatalogSearchResult(
                dataset_id=item.dataset_id,
                name=item.name,
                publisher=item.publisher,
                official_publisher_id=item.official_publisher_id,
                publisher_verification_status=item.publisher_verification_status,
                pii_risk_level=item.pii_risk_level,
                eligibility_status=item.eligibility_status,
                eligibility_reasons=item.eligibility_reasons,
                similarity=item.similarity,
                row_count=item.row_count,
                data_updated_at=_isoformat(item.data_updated_at),
                latest_observed_cutoff_at=_isoformat(item.latest_observed_cutoff_at),
                metadata_synced_at=_isoformat(item.metadata_synced_at) or "",
                index_stale=item.index_stale,
                columns_preview=item.columns_preview,
            )
            for item in summary.results
        ],
    )


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


# --- T-300: PoC de durabilidad ----------------------------------------------
# Prefijo `_poc` deliberado: NO es el contrato final de T-304
# (contracts/api-rest.md `/v2/agent/...`), que incluira RespuestaFinal,
# claims, evidencia y autorizacion `Authorization: Bearer` (RF-801). Este
# PoC demuestra solo la mecanica de durabilidad de plan.md §11 sobre un
# grafo de juguete de 3 nodos; T-304 reutilizara `app/agent/durability.py`,
# `worker_lease.py`, `heartbeat_sweep.py` y `runner.py`.


class PocAgentQueryRequest(BaseModel):
    question: str | None = None
    step_delay_s: Annotated[float, Field(ge=0, le=30)] = runner.DEFAULT_STEP_DELAY_S


class PocAgentQueryResponse(BaseModel):
    run_id: uuid.UUID
    stream_url: str


@app.post(
    "/v2/_poc/agent/query",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PocAgentQueryResponse,
)
async def poc_agent_query(request: Request, body: PocAgentQueryRequest) -> PocAgentQueryResponse:
    """T-300: crea una corrida del grafo de juguete de 3 nodos (plan.md §11)."""

    settings = request.app.state.settings
    worker_instance_id = request.app.state.worker_instance_id
    run_id = await _create_run_with_platform_loop(
        settings.sqlalchemy_database_url,
        worker_instance_id=worker_instance_id,
        question=body.question or "Demostracion T-300 de durabilidad",
        retention_user_days=settings.retention_user_days,
    )
    runner.start_toy_run_task(
        settings.sqlalchemy_database_url,
        settings.psycopg_database_url,
        run_id,
        body.step_delay_s,
    )
    return PocAgentQueryResponse(run_id=run_id, stream_url=f"/v2/_poc/agent/stream/{run_id}")


async def _create_run_with_platform_loop(
    database_url: str, *, worker_instance_id: str, question: str, retention_user_days: int
) -> uuid.UUID:
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_create_run_with_selector,
            database_url,
            worker_instance_id,
            question,
            retention_user_days,
        )
    return await _create_run_async(database_url, worker_instance_id, question, retention_user_days)


def _run_create_run_with_selector(
    database_url: str, worker_instance_id: str, question: str, retention_user_days: int
) -> uuid.UUID:
    return asyncio.run(
        _create_run_async(database_url, worker_instance_id, question, retention_user_days),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _create_run_async(
    database_url: str, worker_instance_id: str, question: str, retention_user_days: int
) -> uuid.UUID:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        return await runner.create_run(
            engine,
            worker_instance_id=worker_instance_id,
            question=question,
            retention_user_days=retention_user_days,
        )
    finally:
        await engine.dispose()


@app.get("/v2/_poc/agent/stream/{run_id}")
async def poc_agent_stream(
    request: Request,
    run_id: uuid.UUID,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """SSE con reconexion `Last-Event-ID` (RF-209, plan.md §11): reenvia los
    eventos persistidos con `seq` mayor y continua en vivo hasta el terminal."""

    settings = request.app.state.settings
    try:
        since_seq = int(last_event_id) if last_event_id else 0
    except ValueError:
        since_seq = 0

    run = await _get_run_with_platform_loop(settings.sqlalchemy_database_url, run_id)
    if run is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "RUN_NOT_FOUND",
            "No se encontro la investigacion solicitada.",
            message_dev=f"run_id={run_id} no existe.",
        )

    return StreamingResponse(
        _poc_sse_generator(settings.sqlalchemy_database_url, run_id, since_seq),
        media_type="text/event-stream",
    )


async def _poc_sse_generator(database_url: str, run_id: uuid.UUID, since_seq: int):
    last_seq = since_seq
    last_ping = asyncio.get_running_loop().time()
    while True:
        events, run = await _fetch_stream_batch_with_platform_loop(database_url, run_id, last_seq)
        if run is None:
            return
        for event in events:
            yield (
                f"id: {event.seq}\nevent: {event.event_type}\n"
                f"data: {json.dumps(event.payload)}\n\n"
            )
            last_seq = event.seq
            if event.event_type in ("answer", "error"):
                return
        if run.status != "running" and not events:
            return
        now = asyncio.get_running_loop().time()
        if now - last_ping >= POC_SSE_PING_INTERVAL_S:
            yield ": ping\n\n"
            last_ping = now
        await asyncio.sleep(POC_SSE_POLL_INTERVAL_S)


async def _get_run_with_platform_loop(database_url: str, run_id: uuid.UUID) -> AgentRun | None:
    if sys.platform == "win32":
        return await asyncio.to_thread(_run_get_run_with_selector, database_url, run_id)
    return await _get_run_async(database_url, run_id)


def _run_get_run_with_selector(database_url: str, run_id: uuid.UUID) -> AgentRun | None:
    return asyncio.run(_get_run_async(database_url, run_id), loop_factory=asyncio.SelectorEventLoop)


async def _get_run_async(database_url: str, run_id: uuid.UUID) -> AgentRun | None:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        return await durability.get_run(engine, run_id)
    finally:
        await engine.dispose()


async def _fetch_stream_batch_with_platform_loop(
    database_url: str, run_id: uuid.UUID, since_seq: int
):
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_fetch_stream_batch_with_selector, database_url, run_id, since_seq
        )
    return await _fetch_stream_batch_async(database_url, run_id, since_seq)


def _run_fetch_stream_batch_with_selector(database_url: str, run_id: uuid.UUID, since_seq: int):
    return asyncio.run(
        _fetch_stream_batch_async(database_url, run_id, since_seq),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _fetch_stream_batch_async(database_url: str, run_id: uuid.UUID, since_seq: int):
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        run = await durability.get_run(engine, run_id)
        if run is None:
            return [], None
        events = await durability.list_events_since(engine, run_id, since_seq)
        return events, run
    finally:
        await engine.dispose()


@app.delete("/v2/_poc/agent/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def poc_delete_agent_run(request: Request, run_id: uuid.UUID) -> Response:
    """RF-803: cancela cooperativamente si esta activa (DELETE_ACTIVE_GRACE_S)
    y borra corrida + checkpoints (`adelete_thread`) de forma irreversible."""

    settings = request.app.state.settings
    run = await _get_run_with_platform_loop(settings.sqlalchemy_database_url, run_id)
    if run is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "RUN_NOT_FOUND",
            "No se encontro la investigacion solicitada.",
            message_dev=f"run_id={run_id} no existe.",
        )

    await runner.request_cancel_and_wait(run_id, settings.delete_active_grace_s)
    await _delete_run_with_platform_loop(
        settings.sqlalchemy_database_url, settings.psycopg_database_url, run_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _delete_run_with_platform_loop(
    sqlalchemy_database_url: str, psycopg_database_url: str, run_id: uuid.UUID
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_delete_run_with_selector, sqlalchemy_database_url, psycopg_database_url, run_id
        )
    else:
        await _delete_run_async(sqlalchemy_database_url, psycopg_database_url, run_id)


def _run_delete_run_with_selector(
    sqlalchemy_database_url: str, psycopg_database_url: str, run_id: uuid.UUID
) -> None:
    asyncio.run(
        _delete_run_async(sqlalchemy_database_url, psycopg_database_url, run_id),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _delete_run_async(
    sqlalchemy_database_url: str, psycopg_database_url: str, run_id: uuid.UUID
) -> None:
    """Orden normativo (plan.md §11/data-model.md §7): checkpoints primero,
    luego la fila de la corrida."""

    async with AsyncPostgresSaver.from_conn_string(psycopg_database_url) as saver:
        await saver.adelete_thread(str(run_id))
    engine = create_app_async_engine(sqlalchemy_database_url, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session, session.begin():
            await session.execute(delete(AgentRun).where(AgentRun.id == run_id))
    finally:
        await engine.dispose()
