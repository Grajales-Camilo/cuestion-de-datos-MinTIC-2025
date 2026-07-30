import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr

import app.main as main


def settings():
    return SimpleNamespace(
        sqlalchemy_database_url="postgresql+psycopg://unused",
        embedding_model="gemini-embedding-2",
        google_api_key=SecretStr("unused"),
    )


async def test_resource_factory_creates_once_and_close_is_idempotent() -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    engine_factory = Mock(return_value=engine)
    client = object()
    client_factory = Mock(return_value=client)

    resources = await main.create_catalog_search_resources(
        settings(), engine_factory=engine_factory, client_factory=client_factory
    )

    assert resources.engine is engine
    assert resources.embedding_client is client
    engine_factory.assert_called_once()
    client_factory.assert_called_once()
    await resources.close()
    await resources.close()
    engine.dispose.assert_awaited_once()


async def test_partial_startup_failure_disposes_engine() -> None:
    engine = SimpleNamespace(dispose=AsyncMock())

    with pytest.raises(RuntimeError, match="cliente"):
        await main.create_catalog_search_resources(
            settings(),
            engine_factory=Mock(return_value=engine),
            client_factory=Mock(side_effect=RuntimeError("cliente")),
        )

    engine.dispose.assert_awaited_once()


async def test_concurrent_lazy_initialization_happens_once(monkeypatch) -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    resources = SimpleNamespace(closed=False)
    created = 0

    async def create(_settings):
        nonlocal created
        created += 1
        await asyncio.sleep(0)
        return resources

    monkeypatch.setattr(main, "create_catalog_search_resources", create)
    observed = await asyncio.gather(
        *(main.get_catalog_search_resources(app, settings()) for _ in range(10))
    )

    assert observed == [resources] * 10
    assert created == 1


async def test_closed_resources_cannot_be_reused() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(catalog_search_resources=SimpleNamespace(closed=True))
    )

    with pytest.raises(RuntimeError, match="cerrados"):
        await main.get_catalog_search_resources(app, settings())


async def test_search_uses_injected_resources_without_factories(monkeypatch) -> None:
    resources = SimpleNamespace(engine=object(), embedding_client=object(), closed=False)
    search = AsyncMock(return_value="summary")
    monkeypatch.setattr(main, "search_catalog", search)

    result = await main.catalog_search_with_platform_loop(
        resources=resources,
        embedding_model="gemini-embedding-2",
        query="educación pública",
        k=10,
        stale_after_days=8,
    )

    assert result == "summary"
    search.assert_awaited_once_with(
        resources.engine,
        embedding_client=resources.embedding_client,
        query="educación pública",
        k=10,
        stale_after_days=8,
        model="gemini-embedding-2",
    )


async def test_lifespan_closes_resources_without_requests(monkeypatch) -> None:
    lifecycle_settings = SimpleNamespace(
        **vars(settings()),
        worker_lease_ttl_s=30,
        run_heartbeat_timeout_s=60,
        run_max_duration_s=75,
    )
    resources = SimpleNamespace(close=AsyncMock(), closed=False)
    monkeypatch.setattr(main, "get_settings", Mock(return_value=lifecycle_settings))
    monkeypatch.setattr(main, "setup_checkpointer", AsyncMock())
    monkeypatch.setattr(main, "create_catalog_search_resources", AsyncMock(return_value=resources))
    monkeypatch.setattr(
        main, "_startup_worker_lifecycle_with_platform_loop", AsyncMock(return_value=("worker", 0))
    )
    monkeypatch.setattr(main, "_mark_worker_shutdown_with_platform_loop", AsyncMock())

    async with main.lifespan(main.app):
        assert main.app.state.catalog_search_resources is resources

    main.create_catalog_search_resources.assert_awaited_once_with(lifecycle_settings)
    resources.close.assert_awaited_once()


async def test_lifespan_startup_failure_closes_created_resources(monkeypatch) -> None:
    lifecycle_settings = SimpleNamespace(
        **vars(settings()),
        worker_lease_ttl_s=30,
        run_heartbeat_timeout_s=60,
        run_max_duration_s=75,
    )
    resources = SimpleNamespace(close=AsyncMock(), closed=False)
    monkeypatch.setattr(main, "get_settings", Mock(return_value=lifecycle_settings))
    monkeypatch.setattr(main, "setup_checkpointer", AsyncMock())
    monkeypatch.setattr(main, "create_catalog_search_resources", AsyncMock(return_value=resources))
    monkeypatch.setattr(
        main,
        "_startup_worker_lifecycle_with_platform_loop",
        AsyncMock(side_effect=RuntimeError("startup")),
    )

    with pytest.raises(RuntimeError, match="startup"):
        async with main.lifespan(main.app):
            pass

    resources.close.assert_awaited_once()
