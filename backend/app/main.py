import asyncio
import hmac
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.checkpointer import setup_checkpointer
from app.db.publishers import (
    DEFAULT_FIXTURE_PATH,
    OfficialPublishersFixture,
    ReloadSummary,
    load_fixture,
    reload_official_publishers,
)
from app.schemas import (
    CatalogIndexCheck,
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
    engine = create_async_engine(database_url, pool_pre_ping=True)
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
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        return await reload_official_publishers(engine, fixture)
    finally:
        await engine.dispose()
