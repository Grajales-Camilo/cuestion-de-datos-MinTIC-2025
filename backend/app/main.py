import asyncio
import hmac
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy import text

from app.catalog.search import CatalogSearchSummary, search_catalog
from app.config import get_settings
from app.db.checkpointer import setup_checkpointer
from app.db.engine import create_app_async_engine
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

APP_VERSION = "2.0.0"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    await setup_checkpointer(settings)
    yield


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
