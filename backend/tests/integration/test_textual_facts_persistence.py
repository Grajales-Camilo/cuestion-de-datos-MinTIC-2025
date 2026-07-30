"""Persistencia aislada T-615C contra PostgreSQL real (RF-703/RF-803/RF-804)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import retention_sweep
from app.agent.persistence import load_textual_facts, persist_textual_facts
from app.config import normalize_database_url_for_sqlalchemy
from app.db.checkpointer import setup_checkpointer
from app.db.models import (
    AgentRun,
    CatalogDataset,
    EvalCase,
    EvalCaseResult,
    EvalRun,
    EvalSuite,
    EvidenceResult,
)
from app.db.models import TextualFact as TextualFactRecord
from app.quality.grounded_facts import TextualFact

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATASET_ID = "txft-0001"
QUESTION_PREFIX = "T-615C"
RETENTION_HASH_SALT = "t615c-retention-hash-salt-32-bytes"


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


async def _clean(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM agent_runs WHERE question LIKE :prefix"),
            {"prefix": f"{QUESTION_PREFIX}%"},
        )
        await connection.execute(
            text(
                "DELETE FROM eval_case_results WHERE eval_run_id IN "
                "(SELECT id FROM eval_runs WHERE git_commit = 't615c-test')"
            )
        )
        await connection.execute(text("DELETE FROM eval_runs WHERE git_commit = 't615c-test'"))
        await connection.execute(
            text(
                "DELETE FROM eval_cases WHERE suite_id IN "
                "(SELECT id FROM eval_suites WHERE name LIKE 't615c-%')"
            )
        )
        await connection.execute(text("DELETE FROM eval_suites WHERE name LIKE 't615c-%'"))
        await connection.execute(
            text("DELETE FROM technical_metrics WHERE llm_model = 't615c-test'")
        )
        await connection.execute(
            text("DELETE FROM catalog_datasets WHERE id = :dataset_id"),
            {"dataset_id": DATASET_ID},
        )


@pytest.fixture(autouse=True)
async def clean_rows(engine):
    await _clean(engine)
    yield
    await _clean(engine)


async def _seed_run_and_evidence(
    engine,
    *,
    created_at: datetime | None = None,
    retention_class: str = "user",
) -> tuple[uuid.UUID, uuid.UUID]:
    now = created_at or datetime.now(UTC)
    run_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        dataset = await session.get(CatalogDataset, DATASET_ID)
        if dataset is None:
            session.add(
                CatalogDataset(
                    id=DATASET_ID,
                    name="Dataset temporal T-615C",
                    publisher="Entidad temporal",
                    publisher_verification_status="verified",
                    metadata_synced_at=now,
                    api_active=True,
                    pii_risk_level="low",
                    eligibility_status="eligible",
                    eligibility_reasons=[],
                )
            )
            await session.flush()
        session.add(
            AgentRun(
                id=run_id,
                question=f"{QUESTION_PREFIX} {run_id}",
                status="completed",
                worker_instance_id=None,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash="x" * 64,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class=retention_class,
                llm_provider="google",
                llm_model="t615c-test",
                steps_used=1,
                latency_ms=1,
                input_tokens=1,
                output_tokens=1,
                estimated_cost_usd=0,
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            EvidenceResult(
                id=evidence_id,
                run_id=run_id,
                dataset_id=DATASET_ID,
                soql_query="SELECT municipio LIMIT 1",
                executed_at=now,
                source_url="https://example.test/resource/txft-0001.json",
                rows=[{"municipio": "Medellín"}],
                row_count=1,
                data_cutoff_basis="unknown",
                citation={"dataset_id": DATASET_ID},
            )
        )
    return run_id, evidence_id


def _fact(
    evidence_id: uuid.UUID,
    *,
    fact_id: uuid.UUID | None = None,
    dataset_id: str = DATASET_ID,
    display_value: str = "Medellín",
) -> TextualFact:
    return TextualFact.model_validate(
        {
            "fact_id": fact_id or uuid.uuid4(),
            "fact_kind": "textual",
            "fact": f"El municipio observado es {display_value}.",
            "operation": "direct_text",
            "evidence_id": evidence_id,
            "dataset_id": dataset_id,
            "source_row_indexes": [0],
            "columns": ["municipio"],
            "raw_values": [display_value],
            "normalized_values": [display_value.casefold()],
            "display_value": display_value,
            "normalization_profile": "text-es-v1",
            "operation_params": {},
            "algorithm_version": "textual-fact-v1",
            "source_hash": f"sha256-jcs-v1:{'a' * 64}",
        }
    )


def _record(
    base_run_id: uuid.UUID,
    base_evidence_id: uuid.UUID,
    **overrides: object,
) -> TextualFactRecord:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "run_id": base_run_id,
        "evidence_id": base_evidence_id,
        "fact_text": "El municipio observado es Medellín.",
        "operation": "direct_text",
        "source_row_indexes": [0],
        "columns_used": ["municipio"],
        "raw_values": ["Medellín"],
        "normalized_values": ["medellín"],
        "display_value": "Medellín",
        "normalization_profile": "text-es-v1",
        "operation_params": {},
        "algorithm_version": "textual-fact-v1",
        "source_hash": f"sha256-jcs-v1:{'b' * 64}",
    }
    values.update(overrides)
    return TextualFactRecord(**values)


async def _table_signature(engine, table_name: str) -> dict[str, tuple]:
    async with engine.connect() as connection:
        columns = (
            (
                await connection.execute(
                    text(
                        "SELECT column_name, data_type, udt_name, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :table_name "
                        "ORDER BY ordinal_position"
                    ),
                    {"table_name": table_name},
                )
            )
            .tuples()
            .all()
        )
        constraints = (
            (
                await connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) "
                        "FROM pg_constraint "
                        "WHERE conrelid = to_regclass(:qualified_name) "
                        "ORDER BY conname"
                    ),
                    {"qualified_name": f"public.{table_name}"},
                )
            )
            .tuples()
            .all()
        )
        indexes = (
            (
                await connection.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = :table_name "
                        "ORDER BY indexname"
                    ),
                    {"table_name": table_name},
                )
            )
            .tuples()
            .all()
        )
    return {
        "columns": tuple(columns),
        "constraints": tuple(constraints),
        "indexes": tuple(indexes),
    }


async def test_round_trip_constraints_and_indexes_with_real_postgres(engine) -> None:
    run_id, evidence_id = await _seed_run_and_evidence(engine)
    fact = _fact(
        evidence_id,
        fact_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    same_hash_fact = _fact(
        evidence_id,
        fact_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
    )

    await persist_textual_facts(engine, run_id, (fact, same_hash_fact))
    loaded = await load_textual_facts(engine, run_id)

    assert loaded == (fact, same_hash_fact)
    signature = await _table_signature(engine, "textual_facts")
    column_names = {row[0] for row in signature["columns"]}
    assert column_names == {
        "id",
        "run_id",
        "evidence_id",
        "fact_text",
        "operation",
        "source_row_indexes",
        "columns_used",
        "raw_values",
        "normalized_values",
        "display_value",
        "normalization_profile",
        "operation_params",
        "algorithm_version",
        "source_hash",
    }
    assert "dataset_id" not in column_names
    constraint_names = {row[0] for row in signature["constraints"]}
    assert {
        "ck_textual_facts_operation",
        "ck_textual_facts_source_rows_nonempty",
        "ck_textual_facts_source_rows_nonnegative",
        "ck_textual_facts_columns_nonempty",
        "ck_textual_facts_raw_values_nonempty",
        "ck_textual_facts_normalized_values_nonempty",
        "ck_textual_facts_values_cardinality",
        "ck_textual_facts_fact_text_nonempty",
        "ck_textual_facts_display_value_nonempty",
        "ck_textual_facts_normalization_profile",
        "ck_textual_facts_algorithm_version",
        "ck_textual_facts_source_hash",
        "textual_facts_pkey",
        "textual_facts_run_id_fkey",
        "textual_facts_evidence_id_fkey",
    } <= constraint_names
    index_names = {row[0] for row in signature["indexes"]}
    assert {
        "ix_textual_facts_run_id",
        "ix_textual_facts_evidence_id",
        "ix_textual_facts_source_hash",
    } <= index_names
    source_hash_index = next(
        definition
        for name, definition in signature["indexes"]
        if name == "ix_textual_facts_source_hash"
    )
    assert "UNIQUE" not in source_hash_index


async def test_database_checks_and_foreign_keys_reject_invalid_rows(engine) -> None:
    run_id, evidence_id = await _seed_run_and_evidence(engine)
    invalid_shapes = (
        {"operation": "free_text"},
        {"source_row_indexes": []},
        {"source_row_indexes": [-1]},
        {"columns_used": []},
        {"raw_values": []},
        {"normalized_values": []},
        {"normalized_values": ["medellín", "bogotá"]},
        {"fact_text": ""},
        {"display_value": ""},
        {"normalization_profile": "text-es-v2"},
        {"algorithm_version": "textual-fact-v2"},
        {"source_hash": f"sha256:{'b' * 64}"},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    for overrides in invalid_shapes:
        with pytest.raises(IntegrityError):
            async with session_factory() as session, session.begin():
                session.add(_record(run_id, evidence_id, **overrides))
                await session.flush()

    for overrides in (
        {"run_id": uuid.uuid4()},
        {"evidence_id": uuid.uuid4()},
    ):
        with pytest.raises(IntegrityError):
            async with session_factory() as session, session.begin():
                session.add(_record(run_id, evidence_id, **overrides))
                await session.flush()


async def test_repository_rejects_evidence_run_or_dataset_mismatch(engine) -> None:
    run_id, evidence_id = await _seed_run_and_evidence(engine)
    other_run_id, other_evidence_id = await _seed_run_and_evidence(engine)

    with pytest.raises(ValueError, match="dataset_id"):
        await persist_textual_facts(
            engine,
            run_id,
            (_fact(evidence_id, dataset_id="zzzz-9999"),),
        )
    with pytest.raises(ValueError, match="inexistente"):
        await persist_textual_facts(engine, run_id, (_fact(uuid.uuid4()),))
    with pytest.raises(ValueError, match="misma corrida"):
        await persist_textual_facts(
            engine,
            run_id,
            (_fact(other_evidence_id),),
        )
    assert await load_textual_facts(engine, run_id) == ()
    assert await load_textual_facts(engine, other_run_id) == ()


async def test_cascade_deletes_facts_with_evidence_and_run(engine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    run_id, evidence_id = await _seed_run_and_evidence(engine)
    fact = _fact(evidence_id)
    await persist_textual_facts(engine, run_id, (fact,))
    async with session_factory() as session, session.begin():
        await session.execute(delete(EvidenceResult).where(EvidenceResult.id == evidence_id))
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(TextualFactRecord)
            .where(TextualFactRecord.id == fact.fact_id)
        )
    assert count == 0

    other_run_id, other_evidence_id = await _seed_run_and_evidence(engine)
    other_fact = _fact(other_evidence_id)
    await persist_textual_facts(engine, other_run_id, (other_fact,))
    async with session_factory() as session, session.begin():
        await session.execute(delete(AgentRun).where(AgentRun.id == other_run_id))
    async with session_factory() as session:
        fact_count = await session.scalar(
            select(func.count())
            .select_from(TextualFactRecord)
            .where(TextualFactRecord.id == other_fact.fact_id)
        )
        evidence_count = await session.scalar(
            select(func.count())
            .select_from(EvidenceResult)
            .where(EvidenceResult.id == other_evidence_id)
        )
    assert fact_count == 0
    assert evidence_count == 0


async def _attach_eval_snapshot(
    engine,
    agent_run_id: uuid.UUID,
    now: datetime,
) -> uuid.UUID:
    suite_id = uuid.uuid4()
    case_id = uuid.uuid4()
    eval_run_id = uuid.uuid4()
    result_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            EvalSuite(
                id=suite_id,
                name=f"t615c-{suite_id}",
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            EvalCase(
                id=case_id,
                suite_id=suite_id,
                question="Snapshot T-615C sin contenido textual",
                case_type="negative",
                seed=1,
            )
        )
        await session.flush()
        session.add(
            EvalRun(
                id=eval_run_id,
                suite_id=suite_id,
                git_commit="t615c-test",
                llm_provider="google",
                llm_model="t615c-test",
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
                passed=True,
                status_final="completed",
                metrics={"latency_ms": 1},
                quality_summary={"classification": "alta"},
                evidence_dataset_ids=[DATASET_ID],
                claim_fingerprint_hashes=["sha256:quantitative-only"],
            )
        )
    return result_id


async def test_retention_is_idempotent_and_oe3_snapshots_keep_no_text(engine) -> None:
    await setup_checkpointer(SimpleNamespace(psycopg_database_url=os.environ["DATABASE_URL"]))
    now = datetime(2026, 7, 17, tzinfo=UTC)
    created_at = datetime(1900, 1, 1, tzinfo=UTC)
    run_id, evidence_id = await _seed_run_and_evidence(
        engine,
        created_at=created_at,
        retention_class="eval",
    )
    sentinel = "SECRETO-TEXTUAL-T615C"
    fact = _fact(evidence_id, display_value=sentinel)
    await persist_textual_facts(engine, run_id, (fact,))
    result_id = await _attach_eval_snapshot(engine, run_id, now)
    source_run_hash = hashlib.sha256(f"{run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()

    summary = await retention_sweep.run_retention_sweep(
        engine,
        os.environ["DATABASE_URL"],
        now=now,
        retention_user_days=36_500,
        retention_eval_months=1_200,
        retention_tech_months=1_200,
        retention_hash_salt=RETENTION_HASH_SALT,
    )
    assert summary.executed.eval_runs == 1

    async with engine.connect() as connection:
        fact_count = (
            await connection.execute(
                text("SELECT count(*) FROM textual_facts WHERE id = :id"),
                {"id": fact.fact_id},
            )
        ).scalar_one()
        snapshot = (
            (
                await connection.execute(
                    text(
                        "SELECT agent_run_id, metrics, quality_summary, "
                        "evidence_dataset_ids, claim_fingerprint_hashes "
                        "FROM eval_case_results WHERE id = :id"
                    ),
                    {"id": result_id},
                )
            )
            .mappings()
            .one()
        )
        metric = (
            await connection.execute(
                text(
                    "SELECT to_jsonb(technical_metrics) AS payload "
                    "FROM technical_metrics WHERE source_run_hash = :hash"
                ),
                {"hash": source_run_hash},
            )
        ).scalar_one()
    assert fact_count == 0
    assert snapshot["agent_run_id"] is None
    assert snapshot["claim_fingerprint_hashes"] == ["sha256:quantitative-only"]
    assert sentinel not in json.dumps(dict(snapshot), ensure_ascii=False, default=str)
    assert sentinel not in json.dumps(metric, ensure_ascii=False, default=str)

    repeated = await retention_sweep.run_retention_sweep(
        engine,
        os.environ["DATABASE_URL"],
        now=now,
        retention_user_days=36_500,
        retention_eval_months=1_200,
        retention_tech_months=1_200,
        retention_hash_salt=RETENTION_HASH_SALT,
    )
    assert repeated.executed.eval_runs == 0
    async with engine.connect() as connection:
        metric_count = (
            await connection.execute(
                text("SELECT count(*) FROM technical_metrics WHERE source_run_hash = :hash"),
                {"hash": source_run_hash},
            )
        ).scalar_one()
    assert metric_count == 1


async def test_migration_downgrade_only_removes_textual_facts(engine) -> None:
    quantitative_before = await _table_signature(engine, "quantitative_claims")
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))

    await engine.dispose()
    try:
        await asyncio.to_thread(command.downgrade, config, "20260716_0005")
        async with engine.connect() as connection:
            textual_table = (
                await connection.execute(text("SELECT to_regclass('public.textual_facts')"))
            ).scalar_one_or_none()
        assert textual_table is None
        assert await _table_signature(engine, "quantitative_claims") == quantitative_before
    finally:
        await engine.dispose()
        await asyncio.to_thread(command.upgrade, config, "head")

    async with engine.connect() as connection:
        textual_table = (
            await connection.execute(text("SELECT to_regclass('public.textual_facts')"))
        ).scalar_one()
    assert textual_table == "textual_facts"
    assert await _table_signature(engine, "quantitative_claims") == quantitative_before
