"""T-615E contra PostgreSQL real, sin activación en runtime (RF-401/404/210)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.persistence import (
    _persisted_order_is_total,
    build_verify_persist_textual_facts,
    load_allowed_grounded_facts,
)
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import (
    AgentRun,
    CatalogDataset,
    EvidenceResult,
    QualityReport,
    QuantitativeClaim,
)
from app.db.models import TextualFact as TextualFactRecord
from app.quality.grounded_facts import (
    CategorySelectionParams,
    CategorySelectionRule,
    EmptyTextualFactOperationParams,
    TextualFactOperation,
)
from app.quality.textual_fact_builder import (
    TextualEvidenceSnapshot,
    TextualFactBuildCommand,
    TextualFactError,
    verify_textual_fact,
)
from app.quality.textual_facts import TextualFactSpec

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def created_ids() -> dict[str, list]:
    return {"run_ids": [], "dataset_ids": []}


@pytest.fixture(autouse=True)
async def cleanup_created_rows(engine, created_ids):
    yield
    async with engine.begin() as connection:
        run_ids = created_ids["run_ids"]
        dataset_ids = created_ids["dataset_ids"]
        if run_ids:
            await connection.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
        if dataset_ids:
            await connection.execute(
                delete(CatalogDataset).where(CatalogDataset.id.in_(dataset_ids))
            )


def direct_spec(*, row_index: int = 0) -> TextualFactSpec:
    return TextualFactSpec(
        operation=TextualFactOperation.DIRECT_TEXT,
        source_row_indexes=(row_index,),
        columns=("municipio",),
        operation_params=EmptyTextualFactOperationParams(),
    )


def ordered_category_spec() -> TextualFactSpec:
    return TextualFactSpec(
        operation=TextualFactOperation.CATEGORY_SELECTION,
        source_row_indexes=(0,),
        columns=("dim_1",),
        operation_params=CategorySelectionParams(
            rule=CategorySelectionRule.FIRST_BY_VALIDATED_ORDER
        ),
    )


async def seed_evidence(
    engine,
    created_ids,
    *,
    rows: list[dict[str, object]] | None = None,
    eligibility_status: str = "eligible",
    classification: str = "alta",
    with_quality: bool = True,
    soql_query: str = "SELECT municipio LIMIT 1000 OFFSET 0",
) -> tuple[uuid.UUID, uuid.UUID, str]:
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    dataset_id = f"e615-{uuid.uuid4().hex[:4]}"
    created_ids["run_ids"].append(run_id)
    created_ids["dataset_ids"].append(dataset_id)
    evidence_rows = rows if rows is not None else [{"municipio": "  Medellín  "}]
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            CatalogDataset(
                id=dataset_id,
                name="Dataset aislado T-615E",
                publisher="Entidad de prueba",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                api_active=True,
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                question=f"Prueba aislada T-615E {run_id}",
                status="completed",
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash="x" * 64,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class="user",
                llm_provider="google",
                llm_model="t615e-test-no-llm",
                steps_used=1,
                latency_ms=1,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            EvidenceResult(
                id=evidence_id,
                run_id=run_id,
                dataset_id=dataset_id,
                soql_query=soql_query,
                executed_at=now,
                source_url="https://example.test/resource/e615-test.json",
                rows=evidence_rows,
                row_count=len(evidence_rows),
                data_cutoff_basis="unknown",
                citation={"dataset_id": dataset_id},
            )
        )
        if with_quality:
            session.add(
                QualityReport(
                    evidence_id=evidence_id,
                    score_total=90 if classification != "no_recomendada" else 10,
                    classification=classification,
                    eligibility_status=eligibility_status,
                    eligibility_reasons=[],
                    dim_schema={},
                    dim_completeness={},
                    dim_timeliness={},
                    dim_traceability={},
                    warnings_user=[],
                    validator_version="t615e-test",
                )
            )
    return run_id, evidence_id, dataset_id


def command(evidence_id: uuid.UUID, dataset_id: str, *, row_index: int = 0):
    return TextualFactBuildCommand(
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        spec=direct_spec(row_index=row_index),
    )


async def fact_count(engine, run_id: uuid.UUID) -> int:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(TextualFactRecord)
                .where(TextualFactRecord.run_id == run_id)
            )
            or 0
        )


async def test_build_verify_persist_load_and_reverify_exactly(engine, created_ids) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    fact_id = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")

    loaded = await build_verify_persist_textual_facts(
        engine,
        run_id,
        (command(evidence_id, dataset_id),),
        fact_id_factory=lambda: fact_id,
    )

    assert len(loaded) == 1
    fact = loaded[0]
    assert fact.fact_id == fact_id
    assert fact.raw_values == ("  Medellín  ",)
    assert fact.display_value == "Medellín"
    assert fact.normalized_values == ("medellín",)
    assert fact.fact == "El valor observado es Medellín."
    source = TextualEvidenceSnapshot(
        run_id=run_id,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        canonical_soql="SELECT municipio LIMIT 1000 OFFSET 0",
        rows=({"municipio": "  Medellín  "},),
        eligibility_status="eligible",
        quality_classification="alta",
    )
    assert (
        verify_textual_fact(
            run_id=run_id,
            evidence_id=evidence_id,
            dataset_id=dataset_id,
            snapshot=source,
            spec=direct_spec(),
            fact=fact,
        ).fact
        == fact
    )


async def test_synthesis_loader_reverifies_and_isolates_facts_by_run(
    engine,
    created_ids,
) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    other_run_id, other_evidence_id, other_dataset_id = await seed_evidence(
        engine,
        created_ids,
        rows=[{"municipio": "Cali"}],
    )
    fact_id = uuid.uuid4()
    other_fact_id = uuid.uuid4()
    await build_verify_persist_textual_facts(
        engine,
        run_id,
        (command(evidence_id, dataset_id),),
        fact_id_factory=lambda: fact_id,
    )
    await build_verify_persist_textual_facts(
        engine,
        other_run_id,
        (command(other_evidence_id, other_dataset_id),),
        fact_id_factory=lambda: other_fact_id,
    )

    allowed = await load_allowed_grounded_facts(engine, run_id)

    assert [fact.id for fact in allowed.facts] == [fact_id]
    assert allowed.facts[0].run_id == run_id
    assert allowed.facts[0].evidence_id == evidence_id


async def test_synthesis_loader_excludes_an_altered_persisted_fact(
    engine,
    created_ids,
) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    fact_id = uuid.uuid4()
    await build_verify_persist_textual_facts(
        engine,
        run_id,
        (command(evidence_id, dataset_id),),
        fact_id_factory=lambda: fact_id,
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(TextualFactRecord)
            .where(TextualFactRecord.id == fact_id)
            .values(fact_text="Texto alterado fuera del constructor.")
        )

    allowed = await load_allowed_grounded_facts(engine, run_id)

    assert allowed.facts == ()


@pytest.mark.parametrize(
    ("canonical_soql", "rows", "expected"),
    (
        (
            (
                "SELECT municipio as dim_1, count(*) as metric_1 "
                "ORDER BY dim_1 ASC, metric_1 DESC LIMIT 2 OFFSET 0"
            ),
            (
                {"dim_1": "Bogotá", "metric_1": 2},
                {"dim_1": "Cali", "metric_1": 3},
            ),
            True,
        ),
        (
            ("SELECT municipio as dim_1, count(*) as metric_1 ORDER BY dim_1 ASC LIMIT 2 OFFSET 0"),
            (
                {"dim_1": "Bogotá", "metric_1": 2},
                {"dim_1": "Cali", "metric_1": 3},
            ),
            False,
        ),
        (
            (
                "SELECT municipio as dim_1, count(*) as metric_1 "
                "ORDER BY dim_1 ASC, metric_1 DESC LIMIT 2 OFFSET 0"
            ),
            (
                {"dim_1": "Bogotá", "metric_1": 2},
                {"dim_1": "Bogotá", "metric_1": 2},
            ),
            False,
        ),
    ),
)
def test_persisted_order_certificate_is_rederived_from_query_and_rows(
    canonical_soql: str,
    rows: tuple[dict, ...],
    expected: bool,
) -> None:
    assert (
        _persisted_order_is_total(
            canonical_soql=canonical_soql,
            rows=rows,
            source_row_indexes=(0,),
        )
        is expected
    )


def test_persisted_order_certificate_rejects_operation_without_renderer_aliases() -> None:
    assert not _persisted_order_is_total(
        canonical_soql="SELECT municipio ORDER BY municipio ASC LIMIT 2 OFFSET 0",
        rows=({"municipio": "Bogotá"}, {"municipio": "Cali"}),
        source_row_indexes=(0,),
    )


async def test_synthesis_loader_rederives_order_instead_of_trusting_build_command(
    engine,
    created_ids,
) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(
        engine,
        created_ids,
        rows=[{"dim_1": "Bogotá"}, {"dim_1": "Cali"}],
        soql_query="SELECT municipio as dim_1 ORDER BY municipio ASC LIMIT 2 OFFSET 0",
    )
    fact_id = uuid.uuid4()
    await build_verify_persist_textual_facts(
        engine,
        run_id,
        (
            TextualFactBuildCommand(
                evidence_id=evidence_id,
                dataset_id=dataset_id,
                spec=ordered_category_spec(),
                validated_order_is_total=True,
            ),
        ),
        fact_id_factory=lambda: fact_id,
    )

    allowed = await load_allowed_grounded_facts(engine, run_id)

    assert allowed.facts == ()


@pytest.mark.parametrize(
    ("eligibility_status", "classification", "expected_code"),
    [
        ("blocked", "alta", "textual_evidence_blocked"),
        ("diagnostic_only", "alta", "textual_evidence_diagnostic_only"),
        ("eligible", "no_recomendada", "textual_evidence_not_recommended"),
    ],
)
async def test_rejects_database_quality_states_without_writes(
    engine,
    created_ids,
    eligibility_status: str,
    classification: str,
    expected_code: str,
) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(
        engine,
        created_ids,
        eligibility_status=eligibility_status,
        classification=classification,
    )

    with pytest.raises(TextualFactError) as captured:
        await build_verify_persist_textual_facts(
            engine,
            run_id,
            (command(evidence_id, dataset_id),),
        )
    assert captured.value.code == expected_code
    assert await fact_count(engine, run_id) == 0


async def test_rejects_missing_evidence_quality_other_run_and_dataset(engine, created_ids) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    other_run_id, other_evidence_id, other_dataset_id = await seed_evidence(
        engine,
        created_ids,
    )
    cases = (
        (
            run_id,
            command(uuid.uuid4(), dataset_id),
            "textual_evidence_not_found",
        ),
        (
            run_id,
            command(other_evidence_id, other_dataset_id),
            "textual_evidence_run_mismatch",
        ),
        (
            run_id,
            command(evidence_id, other_dataset_id),
            "textual_dataset_mismatch",
        ),
    )
    for requested_run_id, requested_command, expected_code in cases:
        with pytest.raises(TextualFactError) as captured:
            await build_verify_persist_textual_facts(
                engine,
                requested_run_id,
                (requested_command,),
            )
        assert captured.value.code == expected_code
    assert await fact_count(engine, run_id) == 0
    assert await fact_count(engine, other_run_id) == 0

    qualityless_run, qualityless_evidence, qualityless_dataset = await seed_evidence(
        engine,
        created_ids,
        with_quality=False,
    )
    with pytest.raises(TextualFactError) as captured:
        await build_verify_persist_textual_facts(
            engine,
            qualityless_run,
            (command(qualityless_evidence, qualityless_dataset),),
        )
    assert captured.value.code == "textual_evidence_quality_missing"


async def test_one_invalid_command_rolls_back_the_entire_batch(engine, created_ids) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)

    with pytest.raises(TextualFactError) as captured:
        await build_verify_persist_textual_facts(
            engine,
            run_id,
            (
                command(evidence_id, dataset_id),
                command(evidence_id, dataset_id, row_index=99),
            ),
        )
    assert captured.value.code == "textual_invalid_row_index"
    assert await fact_count(engine, run_id) == 0


async def test_database_failure_is_typed_and_rolls_back_all_rows(engine, created_ids) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    duplicate_id = uuid.uuid4()

    with pytest.raises(TextualFactError) as captured:
        await build_verify_persist_textual_facts(
            engine,
            run_id,
            (
                command(evidence_id, dataset_id),
                command(evidence_id, dataset_id),
            ),
            fact_id_factory=lambda: duplicate_id,
        )
    assert captured.value.code == "textual_persistence_failed"
    assert await fact_count(engine, run_id) == 0


async def test_quantitative_row_and_unrelated_textual_sentinel_survive(engine, created_ids) -> None:
    sentinel_run, sentinel_evidence, sentinel_dataset = await seed_evidence(
        engine,
        created_ids,
        rows=[{"municipio": "Cali"}],
    )
    sentinel_fact_id = uuid.uuid4()
    await build_verify_persist_textual_facts(
        engine,
        sentinel_run,
        (command(sentinel_evidence, sentinel_dataset),),
        fact_id_factory=lambda: sentinel_fact_id,
    )

    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    quantitative_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            QuantitativeClaim(
                id=quantitative_id,
                run_id=run_id,
                evidence_id=evidence_id,
                claim_text="Conteo cuantitativo centinela: 7",
                claim_type="direct",
                source_row_indexes=[0],
                columns_used=["total"],
                formula=None,
                raw_value=Decimal("7"),
                display_value="7",
                unit=None,
                rounding=0,
                source_hash=f"sha256:{'a' * 64}",
            )
        )

    await build_verify_persist_textual_facts(
        engine,
        run_id,
        (command(evidence_id, dataset_id),),
    )

    async with session_factory() as session:
        quantitative = await session.get(QuantitativeClaim, quantitative_id)
        sentinel = await session.get(TextualFactRecord, sentinel_fact_id)
    assert quantitative is not None
    assert quantitative.raw_value == Decimal("7")
    assert quantitative.display_value == "7"
    assert sentinel is not None
    assert sentinel.fact_text == "El valor observado es Cali."


async def test_existing_foreign_key_cascade_still_removes_only_its_fact(
    engine,
    created_ids,
) -> None:
    run_id, evidence_id, dataset_id = await seed_evidence(engine, created_ids)
    fact_id = uuid.uuid4()
    await build_verify_persist_textual_facts(
        engine,
        run_id,
        (command(evidence_id, dataset_id),),
        fact_id_factory=lambda: fact_id,
    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await session.execute(delete(EvidenceResult).where(EvidenceResult.id == evidence_id))
    async with session_factory() as session:
        assert await session.get(TextualFactRecord, fact_id) is None
