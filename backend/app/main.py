import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.checkpointer import setup_checkpointer
from app.schemas import CatalogIndexCheck, HealthResponse, LLMProviderCheck

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
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
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
