import re
import uuid
from datetime import UTC, datetime

import pytest

from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    ExecutionMetadata,
    execute_validated_plan,
    persist_deterministic_execution,
)
from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    ValidatedQueryPlan,
    validate_query_plan,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DatasetOption,
    DimensionSelection,
    EligibilityStatus,
    EnumeratedPlanningContext,
    MetricSelection,
    PiiRiskLevel,
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


def validated_identifier_lookup(
    *,
    field_names: tuple[str, ...],
    purpose: str,
) -> ValidatedQueryPlan:
    columns = tuple(
        ColumnOption(
            index=index,
            field_name=field_name,
            display_name=field_name,
            data_type=ColumnDataType.NUMBER,
            pii_risk_level=PiiRiskLevel.LOW,
        )
        for index, field_name in enumerate(field_names)
    )
    planning_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="abcd-1234",
                title="Dataset de códigos",
                publisher="Entidad oficial",
                columns=columns,
            ),
        )
    )
    observed_schema = ObservedDatasetSchema(
        dataset_id="abcd-1234",
        eligibility_status=EligibilityStatus.ELIGIBLE,
        pii_risk_level=PiiRiskLevel.LOW,
        columns=tuple(
            ObservedColumn(
                field_name=column.field_name,
                data_type=column.data_type,
                pii_risk_level=column.pii_risk_level,
            )
            for column in columns
        ),
    )
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=tuple(
            DimensionSelection(
                column=ColumnReference(column_index=index),
                provenance=provenance(),
            )
            for index in range(len(columns))
        ),
        limit=12,
        purpose=purpose,
    )
    return validate_query_plan(plan, context=planning_context, schema=observed_schema)


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
async def test_count_group_by_derives_additional_distinct_count_claim() -> None:
    """T-617B-C13-D4 (pilot-037-calidad-aire, golden-v2, dataset `kekd-7v7h`):
    `QueryOperation.COUNT` no admite `COUNT(DISTINCT)` (ver
    `MetricChoice._shape`), así que "cuántas estaciones distintas aparecen"
    solo podía expresarse como `GROUP BY` + `COUNT(*)` por grupo -- cada
    fila enumera un grupo, pero ninguna produce el escalar "número de
    grupos" pedido. Se deriva un claim adicional contando las filas ya
    persistidas (una por grupo), sin inventar ningún valor."""

    metric = MetricSelection(operation=QueryOperation.COUNT, provenance=provenance())
    plan = sum_plan(
        operation=QueryOperation.COUNT,
        metrics=(metric,),
        order_by=(),
        purpose="count: ¿Cuántas estaciones distintas aparecen para la autoridad AMVA?",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Pasto", "metric_count_1": "7"},
                {"dim_1": "Ipiales", "metric_count_1": "27"},
                {"dim_1": "Tumaco", "metric_count_1": "5"},
            ],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    per_group_values = [
        claim.raw_value
        for claim in result.claims.claims
        if claim.columns_used == ("metric_count_1",)
    ]
    assert per_group_values == [7, 27, 5]
    distinct_count_claims = [
        claim for claim in result.claims.claims if claim.columns_used == ("dim_1",)
    ]
    assert len(distinct_count_claims) == 1
    assert distinct_count_claims[0].raw_value == 3
    assert distinct_count_claims[0].claim_type == "derived"


@pytest.mark.asyncio
async def test_count_group_by_without_distinct_wording_skips_extra_claim() -> None:
    """Sin la señal léxica de "distintos/as", no se agrega ningún claim
    adicional -- el comportamiento existente (un claim por grupo) queda
    intacto."""

    metric = MetricSelection(operation=QueryOperation.COUNT, provenance=provenance())
    plan = sum_plan(
        operation=QueryOperation.COUNT,
        metrics=(metric,),
        order_by=(),
        purpose="count: ¿Cuántos registros hay por estación?",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Pasto", "metric_count_1": "7"},
                {"dim_1": "Ipiales", "metric_count_1": "27"},
            ],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    assert len(result.claims.claims) == 2
    assert all(claim.columns_used == ("metric_count_1",) for claim in result.claims.claims)


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


@pytest.mark.asyncio
async def test_lookup_keeps_valid_numeric_claim_when_context_column_is_text() -> None:
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        limit=1,
        purpose="Consultar valor con contexto",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Pasto", "dim_2": "1250"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    assert [claim.raw_value for claim in result.claims.claims] == [1250]
    assert len(result.claims.rejected) == 1


@pytest.mark.asyncio
async def test_lookup_deduplicates_quantitative_claims_from_duplicate_source_rows() -> None:
    """T-617B-C13-D2 (pilot-022-red-vial, golden-v2, dataset `ie7y-asdn`): un
    LOOKUP sobre un único registro (`codigo_tramo=55ST02`) devolvió tres
    filas fuente idénticas (duplicado de publicación) para una columna
    numérica ("categoria"=1) -- `_claim_specs` generaba un claim por fila sin
    colapsar, repitiendo el mismo valor ya correcto tres veces. Una cuarta
    fila con un valor genuinamente distinto (999) se conserva íntegra."""

    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        limit=4,
        purpose="Consultar valor del tramo",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "1250"}, {"dim_1": "1250"}, {"dim_1": "1250"}, {"dim_1": "999"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())
    assert [claim.raw_value for claim in result.claims.claims] == [1250, 999]
    assert [claim.source_row_indexes for claim in result.claims.claims] == [(0,), (3,)]


@pytest.mark.asyncio
async def test_text_lookup_builds_grounded_presence_claim() -> None:
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        limit=1,
        purpose="Consultar proyecto",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "PRY00062", "dim_2": "IP Ibagué - Cajamarca"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())

    claim = result.claims.claims[0]
    assert claim.raw_value == 1
    assert "municipio=PRY00062" in claim.description
    assert "valor=IP Ibagué - Cajamarca" in claim.description
    assert claim.source_row_indexes == (0,)
    assert claim.source_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_requested_numeric_identifier_becomes_exact_textual_fact() -> None:
    plan = validated_identifier_lookup(
        field_names=("cod_mpio",),
        purpose="Consultar el código del municipio",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "05001"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(
        plan,
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )

    assert result.claims.claims == ()
    assert len(result.textual_facts) == 1
    assert result.textual_facts[0].spec.columns == ("dim_1",)
    assert result.textual_facts[0].spec.source_row_indexes == (0,)


@pytest.mark.asyncio
async def test_multirow_postal_identifiers_preserve_each_source_string() -> None:
    plan = validated_identifier_lookup(
        field_names=("codigo_postal", "zona_postal", "codigo_departamento"),
        purpose="Consultar los códigos postales",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "153.42", "dim_2": "1.534", "dim_3": "15"},
                {"dim_1": "153.427", "dim_2": "1.534", "dim_3": "15"},
            ],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(
        plan,
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )

    assert result.claims.claims == ()
    assert [(item.spec.columns, item.spec.source_row_indexes) for item in result.textual_facts] == [
        (("dim_1",), (0,)),
        (("dim_1",), (1,)),
        (("dim_2",), (0,)),
    ]


@pytest.mark.asyncio
async def test_identifier_is_never_recast_as_presence_count_when_textual_facts_disabled() -> None:
    plan = validated_identifier_lookup(
        field_names=("cod_mpio",),
        purpose="Consultar el código del municipio",
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "05001"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    with pytest.raises(DeterministicExecutionError, match="CLAIMS_REJECTED"):
        await execute_validated_plan(
            plan,
            executor=executor,
            metadata=metadata(),
            textual_facts_enabled=False,
        )


@pytest.mark.asyncio
async def test_persistence_uses_evidence_id_created_by_persistence(monkeypatch) -> None:
    generated_evidence_id = uuid.uuid4()
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Pasto", "metric_sum_1": "1250"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    execution = await execute_validated_plan(
        validated(sum_plan()), executor=executor, metadata=metadata()
    )

    async def fake_persist_evidence(*args, **kwargs):
        captured["draft"] = args[2]
        return {"evidence_id": str(generated_evidence_id)}

    async def fake_persist_claims(*args, **kwargs):
        captured["run_id"] = args[1]
        captured["evidence_id"] = args[2]
        captured["claims"] = args[4]
        return [{"claim_id": str(uuid.uuid4())}]

    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.persist_evidence_and_quality",
        fake_persist_evidence,
    )
    monkeypatch.setattr("app.agent.deterministic_pipeline.persist_claims", fake_persist_claims)
    persisted = await persist_deterministic_execution(
        execution,
        engine=object(),  # type: ignore[arg-type]
        run_id=run_id,
        official_publisher_id="publisher-1",
    )
    assert captured["run_id"] == run_id
    assert captured["evidence_id"] == generated_evidence_id
    assert captured["claims"] == execution.claims.claims
    assert persisted.evidence["evidence_id"] == str(generated_evidence_id)


# --- RF-212: etiquetado semántico de extremo a extremo (T-617C) --------------

_INTERNAL_ALIAS_PATTERN = re.compile(r"^(dim_\d+|metric_[a-z]+_\d+|group_count)$")


@pytest.mark.asyncio
async def test_pipeline_resolves_real_column_name_for_metric_claim() -> None:
    """El nombre público del claim debe ser la columna fuente real (`valor`,
    RF-212), nunca el alias `metric_sum_1` usado para leer la fila."""

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Pasto", "metric_sum_1": "1250"}],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    result = await execute_validated_plan(
        validated(sum_plan()), executor=executor, metadata=metadata()
    )

    claim = result.claims.claims[0]
    assert claim.columns_used == ("metric_sum_1",)
    assert claim.public_columns == ("valor",)
    assert claim.label == "Valor"
    assert claim.label_status == "verified"
    assert not _INTERNAL_ALIAS_PATTERN.match(claim.public_columns[0])


@pytest.mark.asyncio
async def test_pipeline_never_leaks_internal_alias_into_public_columns() -> None:
    """Regresión genérica (pruebas.md §4.6): ningún claim del pipeline real
    expone un `public_columns` con forma de alias interno, sin importar
    cuántas columnas/filas tenga el resultado."""

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Pasto", "dim_2": "1250"},
                {"dim_1": "Ibagué", "dim_2": "980"},
            ],
            "source_url": "https://example.test/resource/abcd-1234.json",
        }

    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        limit=2,
        purpose="Consultar municipios",
    )
    result = await execute_validated_plan(validated(plan), executor=executor, metadata=metadata())

    assert result.claims.claims
    for claim in result.claims.claims:
        for name in claim.public_columns:
            assert not _INTERNAL_ALIAS_PATTERN.match(name), name
