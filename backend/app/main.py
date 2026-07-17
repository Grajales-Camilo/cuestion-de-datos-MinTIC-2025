import asyncio
import contextlib
import hashlib
import hmac
import json
import sys
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent import durability, heartbeat_sweep, retention_sweep, runner, worker_lease
from app.catalog.search import CatalogSearchSummary, search_catalog
from app.config import get_settings
from app.db.checkpointer import setup_checkpointer
from app.db.engine import create_app_async_engine
from app.db.models import AgentRun, AgentRunEvent, AgentStep
from app.db.publishers import (
    DEFAULT_FIXTURE_PATH,
    OfficialPublishersFixture,
    ReloadSummary,
    load_fixture,
    reload_official_publishers,
)
from app.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    CatalogIndexCheck,
    CatalogSearchResponse,
    CatalogSearchResult,
    ErrorDetail,
    ErrorEnvelope,
    HealthResponse,
    LLMProviderCheck,
    PublishersReloadSummary,
    RunResultResponse,
    RunStatusResponse,
    RunUsage,
)

POC_SWEEP_INTERVAL_S = 2.0
POC_LEASE_RENEWAL_MIN_INTERVAL_S = 1.0
POC_SSE_POLL_INTERVAL_S = 0.3
POC_SSE_PING_INTERVAL_S = 15.0

APP_VERSION = "2.0.0"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class CatalogSearchResources:
    """Recursos RNF-010 propiedad del loop principal de este worker."""

    def __init__(self, engine: AsyncEngine, embedding_client: object) -> None:
        self.engine = engine
        self.embedding_client = embedding_client
        self.closed = False

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.engine.dispose()


async def create_catalog_search_resources(
    settings,
    *,
    engine_factory: Callable[..., AsyncEngine] = create_app_async_engine,
    client_factory: Callable[..., object] = GoogleGenerativeAIEmbeddings,
) -> CatalogSearchResources:
    engine = engine_factory(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        client = client_factory(
            model=settings.embedding_model,
            google_api_key=settings.google_api_key,
        )
    except BaseException:
        await engine.dispose()
        raise
    return CatalogSearchResources(engine, client)


async def get_catalog_search_resources(app: FastAPI, settings) -> CatalogSearchResources:
    resources = getattr(app.state, "catalog_search_resources", None)
    if resources is not None:
        if resources.closed:
            raise RuntimeError("Los recursos de búsqueda de catálogo ya fueron cerrados.")
        return resources
    lock = getattr(app.state, "catalog_search_resources_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.catalog_search_resources_lock = lock
    async with lock:
        resources = getattr(app.state, "catalog_search_resources", None)
        if resources is None:
            resources = await create_catalog_search_resources(settings)
            app.state.catalog_search_resources = resources
        if resources.closed:
            raise RuntimeError("Los recursos de búsqueda de catálogo ya fueron cerrados.")
        return resources


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    await setup_checkpointer(settings)

    catalog_resources = None
    if (
        settings.google_api_key is not None
        and settings.google_api_key.get_secret_value()
        and settings.embedding_model is not None
    ):
        catalog_resources = await create_catalog_search_resources(settings)
    app.state.catalog_search_resources = catalog_resources
    app.state.catalog_search_resources_lock = asyncio.Lock()

    try:
        worker_instance_id, _closed_on_startup = await _startup_worker_lifecycle_with_platform_loop(
            settings.sqlalchemy_database_url, settings.worker_lease_ttl_s
        )
    except BaseException:
        if catalog_resources is not None:
            await catalog_resources.close()
        raise
    app.state.worker_instance_id = worker_instance_id
    app.state.run_creation_lock = asyncio.Lock()

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

    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        for task in background_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        try:
            await _mark_worker_shutdown_with_platform_loop(
                settings.sqlalchemy_database_url, worker_instance_id
            )
        finally:
            if catalog_resources is not None:
                await catalog_resources.close()


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


@app.post(
    "/v2/admin/retention/run",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin_token)],
)
async def run_admin_retention_sweep(request: Request) -> dict[str, object]:
    """T-306/RF-804: ejecuta manualmente el barrido idempotente de retención."""

    settings = request.app.state.settings
    summary = await _run_retention_sweep_with_platform_loop(
        settings.sqlalchemy_database_url,
        settings.psycopg_database_url,
        now=datetime.now(UTC),
        retention_user_days=settings.retention_user_days,
        retention_eval_months=settings.retention_eval_months,
        retention_tech_months=settings.retention_tech_months,
        retention_hash_salt=_require_retention_hash_salt(settings),
    )
    return summary.as_api_response()


async def _run_retention_sweep_with_platform_loop(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    *,
    now: datetime,
    retention_user_days: int,
    retention_eval_months: int,
    retention_tech_months: int,
    retention_hash_salt: str,
) -> retention_sweep.RetentionSweepSummary:
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_retention_sweep_with_selector,
            sqlalchemy_database_url,
            psycopg_database_url,
            now,
            retention_user_days,
            retention_eval_months,
            retention_tech_months,
            retention_hash_salt,
        )
    return await _run_retention_sweep_async(
        sqlalchemy_database_url,
        psycopg_database_url,
        now=now,
        retention_user_days=retention_user_days,
        retention_eval_months=retention_eval_months,
        retention_tech_months=retention_tech_months,
        retention_hash_salt=retention_hash_salt,
    )


def _run_retention_sweep_with_selector(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    now: datetime,
    retention_user_days: int,
    retention_eval_months: int,
    retention_tech_months: int,
    retention_hash_salt: str,
) -> retention_sweep.RetentionSweepSummary:
    return asyncio.run(
        _run_retention_sweep_async(
            sqlalchemy_database_url,
            psycopg_database_url,
            now=now,
            retention_user_days=retention_user_days,
            retention_eval_months=retention_eval_months,
            retention_tech_months=retention_tech_months,
            retention_hash_salt=retention_hash_salt,
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _run_retention_sweep_async(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    *,
    now: datetime,
    retention_user_days: int,
    retention_eval_months: int,
    retention_tech_months: int,
    retention_hash_salt: str,
) -> retention_sweep.RetentionSweepSummary:
    engine = create_app_async_engine(sqlalchemy_database_url, pool_pre_ping=True)
    try:
        return await retention_sweep.run_retention_sweep(
            engine,
            psycopg_database_url,
            now=now,
            retention_user_days=retention_user_days,
            retention_eval_months=retention_eval_months,
            retention_tech_months=retention_tech_months,
            retention_hash_salt=retention_hash_salt,
        )
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
        resources = await get_catalog_search_resources(request.app, settings)
        summary = await catalog_search_with_platform_loop(
            resources=resources,
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
    resources: CatalogSearchResources,
    embedding_model: str,
    query: str,
    k: int,
    stale_after_days: int,
) -> CatalogSearchSummary:
    return await _catalog_search_async(
        resources=resources,
        embedding_model=embedding_model,
        query=query,
        k=k,
        stale_after_days=stale_after_days,
    )


async def _catalog_search_async(
    *,
    resources: CatalogSearchResources,
    embedding_model: str,
    query: str,
    k: int,
    stale_after_days: int,
) -> CatalogSearchSummary:
    return await search_catalog(
        resources.engine,
        embedding_client=resources.embedding_client,
        query=query,
        k=k,
        stale_after_days=stale_after_days,
        model=embedding_model,
    )


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


# --- T-304: contrato publico del agente -------------------------------------


def _run_not_found() -> ApiError:
    return ApiError(
        status.HTTP_404_NOT_FOUND,
        "RUN_NOT_FOUND",
        "No se encontro la investigacion solicitada.",
        message_dev="La corrida no existe o ya fue eliminada.",
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """contracts/api-rest.md §6: la validación HTTP también usa el sobre estándar."""

    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message_user="La solicitud no cumple los requisitos esperados.",
            message_dev="Validacion de request rechazada.",
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=envelope.model_dump(exclude_none=True),
    )


def _require_retention_hash_salt(settings) -> str:
    """RETENTION_HASH_SALT es secreto servidor obligatorio para el borrado
    (plan.md §12, data-model.md §7): sin él no se puede calcular
    `source_run_hash` y no hay forma segura de copiar métricas antes de
    borrar la corrida."""

    salt = getattr(settings, "retention_hash_salt", None)
    value = salt.get_secret_value() if salt else None
    if not value:
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL",
            "No fue posible completar la operación. Intenta de nuevo más tarde.",
            message_dev="RETENTION_HASH_SALT no esta configurado.",
        )
    return value


async def require_run_access(
    request: Request,
    run_id: uuid.UUID,
    authorization: str | None,
) -> AgentRun:
    """RF-801: autoriza una corrida sin revelar si el Bearer es incorrecto.

    Las corridas vencidas se purgan antes de responder 404. El secreto nunca
    aparece en excepciones, logs ni ``message_dev``; la única comparación es
    SHA-256 + ``hmac.compare_digest`` en tiempo constante.
    """

    settings = request.app.state.settings
    run = await _get_run_with_platform_loop(settings.sqlalchemy_database_url, run_id)
    if run is None:
        raise _run_not_found()
    if run.run_access_token_expires_at <= datetime.now(UTC):
        await _delete_run_with_platform_loop(
            settings.sqlalchemy_database_url,
            settings.psycopg_database_url,
            run_id,
            deletion_reason="retention_expired",
            retention_hash_salt=_require_retention_hash_salt(settings),
        )
        raise _run_not_found()

    scheme, _, token = (authorization or "").partition(" ")
    received_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if (
        scheme.lower() != "bearer"
        or not token
        or not hmac.compare_digest(received_hash, run.run_access_token_hash)
    ):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "No autorizado. Verifica el token de acceso de la investigacion.",
            message_dev="Authorization Bearer ausente o invalido.",
        )
    return run


async def _create_public_run_with_platform_loop(
    database_url: str,
    *,
    worker_instance_id: str,
    question: str,
    context_hint: str | None,
    retention_user_days: int,
) -> tuple[uuid.UUID, str, datetime]:
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_create_public_run_with_selector,
            database_url,
            worker_instance_id,
            question,
            context_hint,
            retention_user_days,
        )
    return await _create_public_run_async(
        database_url, worker_instance_id, question, context_hint, retention_user_days
    )


def _run_create_public_run_with_selector(
    database_url: str,
    worker_instance_id: str,
    question: str,
    context_hint: str | None,
    retention_user_days: int,
) -> tuple[uuid.UUID, str, datetime]:
    return asyncio.run(
        _create_public_run_async(
            database_url, worker_instance_id, question, context_hint, retention_user_days
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _create_public_run_async(
    database_url: str,
    worker_instance_id: str,
    question: str,
    context_hint: str | None,
    retention_user_days: int,
) -> tuple[uuid.UUID, str, datetime]:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        return await runner.create_public_run(
            engine,
            worker_instance_id=worker_instance_id,
            question=question,
            context_hint=context_hint,
            retention_user_days=retention_user_days,
        )
    finally:
        await engine.dispose()


async def _emit_run_started_with_platform_loop(database_url: str, run_id: uuid.UUID) -> None:
    """Hace observable el inicio antes de la primera llamada remota del grafo (RNF-008)."""

    if sys.platform == "win32":
        await asyncio.to_thread(_run_emit_run_started_with_selector, database_url, run_id)
    else:
        await _emit_run_started_async(database_url, run_id)


def _run_emit_run_started_with_selector(database_url: str, run_id: uuid.UUID) -> None:
    asyncio.run(
        _emit_run_started_async(database_url, run_id), loop_factory=asyncio.SelectorEventLoop
    )


async def _emit_run_started_async(database_url: str, run_id: uuid.UUID) -> None:
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        await durability.reserve_and_emit_event(
            engine,
            run_id,
            "step",
            {
                "step_number": 0,
                "node": "start",
                "display_message": "Preparando la investigación.",
                "detail": {},
            },
        )
    finally:
        await engine.dispose()


@app.post(
    "/v2/agent/query",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AgentQueryResponse,
)
async def agent_query(request: Request, body: AgentQueryRequest) -> AgentQueryResponse:
    """RF-201/RF-801: inicia el grafo real T-303 como corrida pública ``user``."""

    settings = request.app.state.settings
    lock = getattr(request.app.state, "run_creation_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.run_creation_lock = lock

    async with lock:
        if len(runner.ACTIVE_RUNS) >= settings.max_concurrent_runs:
            raise ApiError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                "Hay demasiadas investigaciones en curso. Intenta de nuevo en unos minutos.",
                message_dev="MAX_CONCURRENT_RUNS excedido en el proceso actual.",
                retryable=True,
            )

        run_settings = settings
        if body.options is not None:
            overrides = {}
            if body.options.max_steps is not None:
                overrides["agent_max_steps"] = body.options.max_steps
            if settings.eval_mode:
                overrides.update(
                    {
                        name: value
                        for name, value in {
                            "llm_provider": body.options.llm_provider,
                            "llm_model": body.options.llm_model,
                        }.items()
                        if value is not None
                    }
                )
            if overrides:
                run_settings = settings.model_copy(update=overrides)

        run_id, token, expires_at = await _create_public_run_with_platform_loop(
            settings.sqlalchemy_database_url,
            worker_instance_id=request.app.state.worker_instance_id,
            question=body.question,
            context_hint=body.context_hint,
            retention_user_days=settings.retention_user_days,
        )
        await _emit_run_started_with_platform_loop(settings.sqlalchemy_database_url, run_id)
        runner.start_run_task(run_settings, run_id)

    return AgentQueryResponse(
        run_id=str(run_id),
        run_access_token=token,
        token_expires_at=expires_at,
        stream_url=f"/v2/agent/stream/{run_id}",
    )


@app.get("/v2/agent/stream/{run_id}")
async def agent_stream(
    request: Request,
    run_id: uuid.UUID,
    authorization: Annotated[str | None, Header()] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """RF-204/RF-209: SSE durable del grafo real, protegido por Bearer."""

    await require_run_access(request, run_id, authorization)
    try:
        since_seq = max(0, int(last_event_id)) if last_event_id else 0
    except ValueError:
        since_seq = 0
    return StreamingResponse(
        _agent_sse_generator(request.app.state.settings.sqlalchemy_database_url, run_id, since_seq),
        media_type="text/event-stream",
    )


async def _agent_sse_generator(database_url: str, run_id: uuid.UUID, since_seq: int):
    last_seq = since_seq
    last_ping = asyncio.get_running_loop().time()
    while True:
        events, run = await _fetch_stream_batch_with_platform_loop(database_url, run_id, last_seq)
        if run is None:
            return
        for event in events:
            yield (
                f"id: {event.seq}\nevent: {event.event_type}\n"
                f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
            )
            last_seq = event.seq
            if event.event_type in ("answer", "error"):
                return
        if run.status != "running":
            return
        now = asyncio.get_running_loop().time()
        if now - last_ping >= POC_SSE_PING_INTERVAL_S:
            yield ": ping\n\n"
            last_ping = now
        await asyncio.sleep(POC_SSE_POLL_INTERVAL_S)


async def _get_run_detail_with_platform_loop(database_url: str, run_id: uuid.UUID):
    if sys.platform == "win32":
        return await asyncio.to_thread(_run_get_run_detail_with_selector, database_url, run_id)
    return await _get_run_detail_async(database_url, run_id)


def _run_get_run_detail_with_selector(database_url: str, run_id: uuid.UUID):
    return asyncio.run(
        _get_run_detail_async(database_url, run_id), loop_factory=asyncio.SelectorEventLoop
    )


async def _get_run_detail_async(database_url: str, run_id: uuid.UUID):
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            run = await session.get(AgentRun, run_id)
            if run is None:
                return None
            steps = (
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
            events = (
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
            return run, steps, events
    finally:
        await engine.dispose()


def _run_usage(run: AgentRun) -> RunUsage:
    final_answer = run.final_answer if isinstance(run.final_answer, dict) else {}
    usage = final_answer.get("usage") if isinstance(final_answer.get("usage"), dict) else {}
    return RunUsage(
        steps_used=run.steps_used,
        latency_ms=run.latency_ms,
        estimated_cost_usd=float(run.estimated_cost_usd)
        if run.estimated_cost_usd is not None
        else None,
        termination_reason=usage.get("termination_reason") or run.terminal_error_code,
    )


def _step_response(step: AgentStep) -> dict[str, object]:
    return {
        "step_number": step.step_number,
        "node": step.node,
        "display_message": step.display_message,
        "detail": step.tool_output_summary,
    }


def _event_response(event: AgentRunEvent) -> dict[str, object]:
    return {"seq": event.seq, "event": event.event_type, "data": event.payload}


@app.get("/v2/agent/runs/{run_id}", response_model=RunStatusResponse | RunResultResponse)
async def agent_run_status(
    request: Request,
    run_id: uuid.UUID,
    authorization: Annotated[str | None, Header()] = None,
) -> RunStatusResponse | RunResultResponse:
    """RF-801: devuelve el esquema de estado o la RespuestaFinal persistida."""

    await require_run_access(request, run_id, authorization)
    detail = await _get_run_detail_with_platform_loop(
        request.app.state.settings.sqlalchemy_database_url, run_id
    )
    if detail is None:
        raise _run_not_found()
    run, steps, events = detail
    serialized_steps = [_step_response(step) for step in steps]
    serialized_events = [_event_response(event) for event in events]
    if run.status == "running":
        return RunStatusResponse(
            run_id=str(run.id),
            status="running",
            steps=serialized_steps,
            events=serialized_events,
            last_event_seq=run.last_event_seq,
            partial_evidence=[],
            partial_claims=[],
            usage=_run_usage(run),
        )
    answer = run.final_answer if isinstance(run.final_answer, dict) else {}
    return RunResultResponse(
        run_id=str(run.id),
        status=run.status,
        answer=answer,
        steps=serialized_steps,
        events=serialized_events,
        last_event_seq=run.last_event_seq,
    )


@app.delete("/v2/agent/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_run(
    request: Request,
    run_id: uuid.UUID,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """RF-803: cancela cooperativamente y borra checkpoints antes de la fila."""

    await require_run_access(request, run_id, authorization)
    settings = request.app.state.settings
    retention_hash_salt = _require_retention_hash_salt(settings)
    await runner.request_cancel_and_wait(run_id, settings.delete_active_grace_s)
    await _delete_run_with_platform_loop(
        settings.sqlalchemy_database_url,
        settings.psycopg_database_url,
        run_id,
        deletion_reason="user_requested",
        retention_hash_salt=retention_hash_salt,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
                f"id: {event.seq}\nevent: {event.event_type}\ndata: {json.dumps(event.payload)}\n\n"
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
        settings.sqlalchemy_database_url,
        settings.psycopg_database_url,
        run_id,
        deletion_reason="user_requested",
        retention_hash_salt=_require_retention_hash_salt(settings),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _delete_run_with_platform_loop(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    *,
    deletion_reason: durability.DeletionReason,
    retention_hash_salt: str,
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_delete_run_with_selector,
            sqlalchemy_database_url,
            psycopg_database_url,
            run_id,
            deletion_reason,
            retention_hash_salt,
        )
    else:
        await _delete_run_async(
            sqlalchemy_database_url,
            psycopg_database_url,
            run_id,
            deletion_reason=deletion_reason,
            retention_hash_salt=retention_hash_salt,
        )


def _run_delete_run_with_selector(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    deletion_reason: durability.DeletionReason,
    retention_hash_salt: str,
) -> None:
    asyncio.run(
        _delete_run_async(
            sqlalchemy_database_url,
            psycopg_database_url,
            run_id,
            deletion_reason=deletion_reason,
            retention_hash_salt=retention_hash_salt,
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _delete_run_async(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    *,
    deletion_reason: durability.DeletionReason,
    retention_hash_salt: str,
) -> None:
    """Adaptador Windows para la operación compartida de RF-803/RF-804."""

    engine = create_app_async_engine(sqlalchemy_database_url, pool_pre_ping=True)
    try:
        await durability.delete_run_with_checkpoints(
            engine,
            psycopg_database_url,
            run_id,
            deletion_reason=deletion_reason,
            retention_hash_salt=retention_hash_salt,
        )
    finally:
        await engine.dispose()
