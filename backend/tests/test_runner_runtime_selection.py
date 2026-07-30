import uuid
from unittest.mock import AsyncMock

import pytest

import app.agent.runner as runner
from app.config import Settings


def _settings(runtime: str) -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql://usuario:clave@localhost:5432/cuestion_de_datos",
        RETENTION_HASH_SALT="replace-with-local-development-salt-32-bytes",
        AGENT_RUNTIME=runtime,
    )


@pytest.mark.asyncio
async def test_default_dispatches_only_to_deterministic_runtime(monkeypatch) -> None:
    deterministic = AsyncMock(return_value={"runtime": "deterministic"})
    legacy = AsyncMock(return_value={"runtime": "legacy"})
    monkeypatch.setattr(runner, "execute_deterministic_agent_run_async", deterministic)
    monkeypatch.setattr(runner, "execute_legacy_agent_run_async", legacy)

    result = await runner.execute_agent_run_async(_settings("deterministic"), uuid.uuid4())

    assert result["runtime"] == "deterministic"
    deterministic.assert_awaited_once()
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_runtime_requires_explicit_configuration(monkeypatch) -> None:
    deterministic = AsyncMock(return_value={"runtime": "deterministic"})
    legacy = AsyncMock(return_value={"runtime": "legacy"})
    monkeypatch.setattr(runner, "execute_deterministic_agent_run_async", deterministic)
    monkeypatch.setattr(runner, "execute_legacy_agent_run_async", legacy)

    result = await runner.execute_agent_run_async(_settings("legacy"), uuid.uuid4())

    assert result["runtime"] == "legacy"
    legacy.assert_awaited_once()
    deterministic.assert_not_awaited()
