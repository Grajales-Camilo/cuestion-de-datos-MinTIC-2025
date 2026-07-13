from datetime import UTC, datetime

import pytest

from app.agent.deterministic_pipeline import ExecutionMetadata, execute_validated_plan
from app.agent.plan_validator import validate_query_plan
from app.agent.query_plan import (
    ColumnReference,
    DimensionSelection,
    MetricSelection,
    QueryOperation,
    QueryPlan,
)
from tests.test_query_plan import context, provenance, sum_plan
from tests.test_soql_renderer import schema


def metadata(*, medium: bool = False) -> ExecutionMetadata:
    return ExecutionMetadata(
        dataset_name="Dataset de prueba",
        publisher="Entidad oficial",
        dataset_pii_risk_level="medium" if medium else "low",
        dataset_eligibility_status="eligible",
        dataset_eligibility_reasons=("pii_medium_requires_aggregation",) if medium else (),
        data_updated_at=datetime.now(UTC),
    )


def validated(plan: QueryPlan, *, medium: bool = False):
    return validate_query_plan(plan, context=context(), schema=schema(medium=medium))


@pytest.mark.asyncio
async def test_count_vertical_without_llm() -> None:
    metric = MetricSelection(operation=QueryOperation.COUNT, provenance=provenance())
    plan = sum_plan(operation=QueryOperation.COUNT, metrics=(metric,), order_by=())

    async def executor(payload: dict) -> dict:
        assert "count(*) as metric_count_1" in payload["soql"]
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Pasto", "metric_count_1": "42"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    assert result.claims.claims[0].raw_value == 42
    assert result.claims.rejected == ()


@pytest.mark.asyncio
async def test_sum_with_privacy_group_count_without_llm() -> None:
    async def executor(payload: dict) -> dict:
        assert "sum(valor) as metric_sum_1" in payload["soql"]
        assert "count(*) as group_count" in payload["soql"]
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Pasto", "metric_sum_1": "1250", "group_count": "15"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(
        validated(sum_plan(), medium=True), executor=executor, metadata=metadata(medium=True)
    )
    assert result.quality.eligibility_status == "eligible"
    assert result.quality.row_policy.aggregation_min_count == 15
    assert result.claims.claims[0].raw_value == 1250


@pytest.mark.asyncio
async def test_direct_lookup_parses_text_number_with_separators() -> None:
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        filters=sum_plan().filters,
        limit=1,
        purpose="Consultar presupuesto",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "3,893,283,514,468.00"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    assert result.claims.claims[0].raw_value == 3_893_283_514_468
    assert result.claims.claims[0].source_hash.startswith("sha256:")
