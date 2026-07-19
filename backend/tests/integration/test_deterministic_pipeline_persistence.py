import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.deterministic_pipeline import (
    ExecutionMetadata,
    execute_validated_plan,
    persist_deterministic_execution,
)
from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    validate_query_plan,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    DatasetOption,
    EligibilityStatus,
    EnumeratedPlanningContext,
    MetricSelection,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    SelectionOrigin,
    SelectionProvenance,
)
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import (
    AgentRun,
    CatalogColumn,
    CatalogDataset,
    EvidenceResult,
    QualityReport,
    QuantitativeClaim,
    WorkerInstance,
)

pytestmark = pytest.mark.integration
DATASET_ID = "zdet-0001"
QUESTION = "integracion pipeline determinista"


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_rows(engine):
    async def clean() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM agent_runs WHERE question = :question"),
                {"question": QUESTION},
            )
            await connection.execute(
                text("DELETE FROM worker_instances WHERE id LIKE 'det-worker-%'")
            )
            await connection.execute(
                text("DELETE FROM catalog_datasets WHERE id = :dataset_id"),
                {"dataset_id": DATASET_ID},
            )

    await clean()
    yield
    await clean()


async def seed(engine) -> uuid.UUID:
    now = datetime.now(UTC)
    worker_id = f"det-worker-{uuid.uuid4()}"
    run_id = uuid.uuid4()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            WorkerInstance(
                id=worker_id,
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(minutes=5),
                status="active",
            )
        )
        session.add(
            CatalogDataset(
                id=DATASET_ID,
                name="Dataset determinista temporal",
                publisher="Entidad oficial temporal",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                data_updated_at=now,
                api_active=True,
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
        await session.flush()
        session.add(
            CatalogColumn(
                dataset_id=DATASET_ID,
                field_name="total",
                display_name="Total",
                data_type="Number",
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                question=QUESTION,
                status="running",
                worker_instance_id=worker_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash="x" * 16,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class="user",
                created_at=now,
            )
        )
    return run_id


def validated_plan():
    provenance = SelectionProvenance(origin=SelectionOrigin.SCHEMA)
    context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id=DATASET_ID,
                title="Dataset determinista temporal",
                publisher="Entidad oficial temporal",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="total",
                        display_name="Total",
                        data_type=ColumnDataType.NUMBER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(
            MetricSelection(
                operation=QueryOperation.SUM,
                column={"column_index": 0},
                provenance=provenance,
            ),
        ),
        purpose="Sumar total temporal",
    )
    schema = ObservedDatasetSchema(
        dataset_id=DATASET_ID,
        eligibility_status=EligibilityStatus.ELIGIBLE,
        pii_risk_level=PiiRiskLevel.LOW,
        columns=(
            ObservedColumn(
                field_name="total",
                data_type=ColumnDataType.NUMBER,
                pii_risk_level=PiiRiskLevel.LOW,
            ),
        ),
    )
    return validate_query_plan(plan, context=context, schema=schema)


async def test_persists_evidence_quality_and_claims_with_real_postgres(engine) -> None:
    run_id = await seed(engine)

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"metric_sum_1": "1250"}],
            "source_url": "https://example.test/resource/zdet-0001.json",
        }

    execution = await execute_validated_plan(
        validated_plan(),
        executor=executor,
        metadata=ExecutionMetadata(
            dataset_name="Dataset determinista temporal",
            publisher="Entidad oficial temporal",
            dataset_pii_risk_level="low",
            dataset_eligibility_status="eligible",
            data_updated_at=datetime.now(UTC),
        ),
    )
    persisted = await persist_deterministic_execution(
        execution,
        engine=engine,
        run_id=run_id,
        official_publisher_id=None,
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    evidence_id = uuid.UUID(persisted.evidence["evidence_id"])
    async with factory() as session:
        evidence_count = await session.scalar(
            select(func.count()).select_from(EvidenceResult).where(EvidenceResult.run_id == run_id)
        )
        quality_count = await session.scalar(
            select(func.count())
            .select_from(QualityReport)
            .where(QualityReport.evidence_id == evidence_id)
        )
        claim = await session.scalar(
            select(QuantitativeClaim).where(QuantitativeClaim.run_id == run_id)
        )
    assert evidence_count == 1
    assert quality_count == 1
    assert claim is not None
    assert claim.evidence_id == evidence_id
    # RF-212 (T-617C-R1): la fila real de `quantitative_claims.columns_used`
    # persiste el nombre de columna fuente real ("total"), nunca el alias de
    # ejecución interno ("metric_sum_1") que solo vive en memoria durante la
    # construcción del claim.
    assert claim.columns_used == ["total"]
    assert persisted.claims[0]["columns"] == ["total"]
    assert persisted.claims[0]["label"] == "Total"
    assert persisted.claims[0]["label_status"] == "verified"
    assert claim.source_hash.startswith("sha256:")
