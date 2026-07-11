"""Integración T-306/RF-804 contra PostgreSQL real con reloj simulado."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import retention_sweep
from app.agent.durability import get_run
from app.config import normalize_database_url_for_sqlalchemy
from app.db.checkpointer import setup_checkpointer
from app.db.models import AgentRun, EvalCase, EvalCaseResult, EvalRun, EvalSuite

pytestmark = pytest.mark.integration

RETENTION_HASH_SALT = "test-retention-hash-salt-32-bytes-integration"


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    await setup_checkpointer(SimpleNamespace(psycopg_database_url=os.environ["DATABASE_URL"]))
    yield engine
    await engine.dispose()


async def _insert_run(engine, *, retention_class: str, created_at: datetime) -> uuid.UUID:
    run_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question="prueba de retención T-306",
                status="completed",
                worker_instance_id=None,
                heartbeat_at=created_at,
                last_event_seq=0,
                run_access_token_hash="x" * 64,
                run_access_token_expires_at=created_at + timedelta(days=1),
                retention_class=retention_class,
                llm_provider="google",
                llm_model="scripted-test",
                steps_used=2,
                latency_ms=12,
                input_tokens=3,
                output_tokens=4,
                estimated_cost_usd=0,
                created_at=created_at,
            )
        )
    return run_id


async def _attach_eval_snapshot(
    engine, agent_run_id: uuid.UUID, now: datetime
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    suite_id = uuid.uuid4()
    case_id = uuid.uuid4()
    eval_run_id = uuid.uuid4()
    result_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(EvalSuite(id=suite_id, name=f"t306-{suite_id}", created_at=now))
        await session.flush()
        session.add(
            EvalCase(
                id=case_id,
                suite_id=suite_id,
                question="Caso de evaluación no identificable",
                case_type="negative",
                seed=1,
            )
        )
        await session.flush()
        session.add(
            EvalRun(
                id=eval_run_id,
                suite_id=suite_id,
                git_commit="test",
                llm_provider="google",
                llm_model="scripted-test",
                eval_seed=1,
                config_snapshot={},
                started_at=now,
            )
        )
        await session.flush()
        session.add(
            EvalCaseResult(
                id=result_id,
                eval_run_id=eval_run_id,
                case_id=case_id,
                agent_run_id=agent_run_id,
                status_final="completed",
                metrics={"latency_ms": 12},
                quality_summary={"classification": "alta"},
                evidence_dataset_ids=["abcd-1234"],
                claim_fingerprint_hashes=["fingerprint"],
                error_code=None,
                failure_reason=None,
            )
        )
    return result_id, suite_id, eval_run_id


async def _clean(
    engine,
    *,
    run_ids: list[uuid.UUID],
    source_hashes: list[str],
    suite_ids: list[uuid.UUID],
):
    async with engine.begin() as connection:
        if run_ids:
            await connection.execute(
                text("DELETE FROM agent_runs WHERE id = ANY(:ids)"), {"ids": run_ids}
            )
        if source_hashes:
            await connection.execute(
                text("DELETE FROM technical_metrics WHERE source_run_hash = ANY(:hashes)"),
                {"hashes": source_hashes},
            )
        if suite_ids:
            await connection.execute(
                text("DELETE FROM eval_suites WHERE id = ANY(:ids)"), {"ids": suite_ids}
            )


async def test_retention_sweep_deletes_expired_runs_metrics_and_eval_snapshot(engine) -> None:
    """pruebas.md §2.3: user/eval, checkpoints, snapshot y métricas vencidas."""

    now = datetime(2026, 7, 10, tzinfo=UTC)
    user_run_id = await _insert_run(
        engine, retention_class="user", created_at=now - timedelta(days=91)
    )
    eval_run_id = await _insert_run(
        engine, retention_class="eval", created_at=now - timedelta(days=24 * 31)
    )
    result_id, suite_id, evaluation_run_id = await _attach_eval_snapshot(engine, eval_run_id, now)
    old_metric_hash = f"old-{uuid.uuid4()}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO technical_metrics "
                "(id, run_month, source_run_hash, retention_class_origin, status_final, "
                "deleted_at, deletion_reason, created_at) "
                "VALUES (:id, '2025-06', :hash, 'user', 'completed', :created, "
                "'retention_expired', :created)"
            ),
            {"id": uuid.uuid4(), "hash": old_metric_hash, "created": now - timedelta(days=366)},
        )

    user_hash = hashlib.sha256(f"{user_run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()
    eval_hash = hashlib.sha256(f"{eval_run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()
    try:
        summary = await retention_sweep.run_retention_sweep(
            engine,
            os.environ["DATABASE_URL"],
            now=now,
            retention_user_days=90,
            retention_eval_months=24,
            retention_tech_months=12,
            retention_hash_salt=RETENTION_HASH_SALT,
        )

        assert summary.planned.as_dict() == {
            "user_runs": 1,
            "eval_runs": 1,
            "technical_metrics": 1,
        }
        assert summary.executed.as_dict() == summary.planned.as_dict()
        assert await get_run(engine, user_run_id) is None
        assert await get_run(engine, eval_run_id) is None

        async with engine.connect() as connection:
            metric_rows = (
                await connection.execute(
                    text(
                        "SELECT source_run_hash, deletion_reason FROM technical_metrics "
                        "WHERE source_run_hash = ANY(:hashes)"
                    ),
                    {"hashes": [user_hash, eval_hash]},
                )
            ).all()
            eval_snapshot = (
                await connection.execute(
                    text(
                        "SELECT agent_run_id, metrics, quality_summary, evidence_dataset_ids, "
                        "claim_fingerprint_hashes FROM eval_case_results WHERE id = :id"
                    ),
                    {"id": result_id},
                )
            ).mappings().one()
            checkpoints = await connection.execute(
                text("SELECT count(*) FROM checkpoints WHERE thread_id = :thread_id"),
                {"thread_id": str(user_run_id)},
            )
        assert {row.source_run_hash for row in metric_rows} == {user_hash, eval_hash}
        assert {row.deletion_reason for row in metric_rows} == {"retention_expired"}
        assert eval_snapshot["agent_run_id"] is None
        assert eval_snapshot["metrics"] == {"latency_ms": 12}
        assert eval_snapshot["quality_summary"] == {"classification": "alta"}
        assert eval_snapshot["evidence_dataset_ids"] == ["abcd-1234"]
        assert eval_snapshot["claim_fingerprint_hashes"] == ["fingerprint"]
        assert checkpoints.scalar_one() == 0

        repeated = await retention_sweep.run_retention_sweep(
            engine,
            os.environ["DATABASE_URL"],
            now=now,
            retention_user_days=90,
            retention_eval_months=24,
            retention_tech_months=12,
            retention_hash_salt=RETENTION_HASH_SALT,
        )
        assert repeated.planned == retention_sweep.RetentionCounts()
        assert repeated.executed == retention_sweep.RetentionCounts()
    finally:
        await _clean(
            engine,
            run_ids=[user_run_id, eval_run_id],
            source_hashes=[user_hash, eval_hash, old_metric_hash],
            suite_ids=[],
        )
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM eval_case_results WHERE id = :id"), {"id": result_id}
            )
            await connection.execute(
                text("DELETE FROM eval_runs WHERE id = :id"), {"id": evaluation_run_id}
            )
            await connection.execute(
                text("DELETE FROM eval_suites WHERE id = :id"), {"id": suite_id}
            )


async def test_two_concurrent_sweeps_allow_one_logical_execution(engine, monkeypatch) -> None:
    """pruebas.md §2.3: dos tareas reales compiten por el advisory lock."""

    now = datetime(2026, 7, 10, tzinfo=UTC)
    run_id = await _insert_run(engine, retention_class="user", created_at=now - timedelta(days=91))
    source_hash = hashlib.sha256(f"{run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()
    started = asyncio.Event()
    release = asyncio.Event()
    original_delete = retention_sweep.delete_run_with_checkpoints

    async def delayed_delete(*args, **kwargs):
        started.set()
        await release.wait()
        return await original_delete(*args, **kwargs)

    monkeypatch.setattr(retention_sweep, "delete_run_with_checkpoints", delayed_delete)
    try:
        first_task = asyncio.create_task(
            retention_sweep.run_retention_sweep(
                engine,
                os.environ["DATABASE_URL"],
                now=now,
                retention_user_days=90,
                retention_eval_months=24,
                retention_tech_months=12,
                retention_hash_salt=RETENTION_HASH_SALT,
            )
        )
        await started.wait()
        second = await retention_sweep.run_retention_sweep(
            engine,
            os.environ["DATABASE_URL"],
            now=now,
            retention_user_days=90,
            retention_eval_months=24,
            retention_tech_months=12,
            retention_hash_salt=RETENTION_HASH_SALT,
        )
        release.set()
        first = await first_task

        assert first.already_running is False
        assert second.already_running is True
        assert second.planned == retention_sweep.RetentionCounts()
        assert await get_run(engine, run_id) is None
    finally:
        release.set()
        await _clean(engine, run_ids=[run_id], source_hashes=[source_hash], suite_ids=[])


async def test_checkpoint_failure_leaves_run_retryable_without_duplicate_metric(
    engine, monkeypatch
) -> None:
    """pruebas.md §2.3: un fallo de checkpoints se puede reintentar sin copias duplicadas."""

    now = datetime(2026, 7, 10, tzinfo=UTC)
    run_id = await _insert_run(engine, retention_class="user", created_at=now - timedelta(days=91))
    source_hash = hashlib.sha256(f"{run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()
    original_delete = retention_sweep.delete_run_with_checkpoints

    async def checkpoint_failure(*_args, **_kwargs):
        raise RuntimeError("fallo simulado de adelete_thread")

    monkeypatch.setattr(retention_sweep, "delete_run_with_checkpoints", checkpoint_failure)
    try:
        with pytest.raises(RuntimeError, match="adelete_thread"):
            await retention_sweep.run_retention_sweep(
                engine,
                os.environ["DATABASE_URL"],
                now=now,
                retention_user_days=90,
                retention_eval_months=24,
                retention_tech_months=12,
                retention_hash_salt=RETENTION_HASH_SALT,
            )
        assert await get_run(engine, run_id) is not None

        monkeypatch.setattr(retention_sweep, "delete_run_with_checkpoints", original_delete)
        retried = await retention_sweep.run_retention_sweep(
            engine,
            os.environ["DATABASE_URL"],
            now=now,
            retention_user_days=90,
            retention_eval_months=24,
            retention_tech_months=12,
            retention_hash_salt=RETENTION_HASH_SALT,
        )
        assert retried.executed.user_runs == 1
        assert await get_run(engine, run_id) is None
        async with engine.connect() as connection:
            metrics = (
                await connection.execute(
                    text("SELECT count(*) FROM technical_metrics WHERE source_run_hash = :hash"),
                    {"hash": source_hash},
                )
            ).scalar_one()
        assert metrics == 1
    finally:
        await _clean(engine, run_ids=[run_id], source_hashes=[source_hash], suite_ids=[])


async def test_admin_endpoint_skips_when_retention_lock_is_taken(engine) -> None:
    """El endpoint devuelve el contrato `skipped/already_running` con el lock real."""

    from httpx import ASGITransport, AsyncClient

    import app.main as main

    main.app.state.settings = SimpleNamespace(
        admin_token=SecretStr("retention-admin-token"),
        sqlalchemy_database_url=normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        psycopg_database_url=os.environ["DATABASE_URL"],
        retention_user_days=90,
        retention_eval_months=24,
        retention_tech_months=12,
        retention_hash_salt=SecretStr(RETENTION_HASH_SALT),
    )
    async with engine.connect() as lock_connection, lock_connection.begin():
        await lock_connection.execute(text("SELECT pg_advisory_xact_lock(20260707, 804)"))
        async with AsyncClient(
            transport=ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v2/admin/retention/run", headers={"X-Admin-Token": "retention-admin-token"}
            )

    assert response.status_code == 202
    assert response.json() == {
        "status": "skipped",
        "reason": "already_running",
        "planned": {"user_runs": 0, "eval_runs": 0, "technical_metrics": 0},
        "executed": {"user_runs": 0, "eval_runs": 0, "technical_metrics": 0},
    }
