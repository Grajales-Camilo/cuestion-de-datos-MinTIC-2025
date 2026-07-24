import pytest
from pydantic import ValidationError

from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
    column_satisfies_named_output_system,
    named_output_system,
    validate_query_plan,
    validate_requested_output_semantics,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DatasetOption,
    DimensionSelection,
    EligibilityStatus,
    EnumeratedPlanningContext,
    FilterOperator,
    FilterSelection,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
)
from tests.test_query_plan import context, provenance, sum_plan


def schema(
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    value_type: ColumnDataType = ColumnDataType.NUMBER,
    value_pii: PiiRiskLevel = PiiRiskLevel.LOW,
) -> ObservedDatasetSchema:
    return ObservedDatasetSchema(
        dataset_id="abcd-1234",
        eligibility_status=eligibility,
        pii_risk_level=value_pii,
        columns=(
            ObservedColumn(
                field_name="municipio",
                data_type=ColumnDataType.TEXT,
                pii_risk_level=PiiRiskLevel.LOW,
            ),
            ObservedColumn(
                field_name="valor",
                data_type=value_type,
                pii_risk_level=value_pii,
            ),
        ),
    )


def assert_code(expected: PlanValidationCode, function: object) -> None:
    with pytest.raises(PlanValidationError) as captured:
        function()  # type: ignore[operator]
    assert captured.value.code is expected


def test_resolves_indexes_to_real_dataset_and_column_names() -> None:
    validated = validate_query_plan(sum_plan(), context=context(), schema=schema())
    assert validated.dataset_id == "abcd-1234"
    assert validated.dimensions[0].field_name == "municipio"
    assert validated.metrics[0].field_name == "valor"
    assert validated.source_plan_hash == sum_plan().plan_hash()
    assert validated.include_group_count is False


def test_rejects_schema_for_a_different_dataset() -> None:
    wrong = schema().model_copy(update={"dataset_id": "wxyz-9876"})
    assert_code(
        PlanValidationCode.DATASET_MISMATCH,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=wrong),
    )


@pytest.mark.parametrize("status", [EligibilityStatus.DIAGNOSTIC_ONLY, EligibilityStatus.BLOCKED])
def test_rejects_dataset_that_is_not_eligible(status: EligibilityStatus) -> None:
    assert_code(
        PlanValidationCode.DATASET_NOT_ELIGIBLE,
        lambda: validate_query_plan(
            sum_plan(), context=context(), schema=schema(eligibility=status)
        ),
    )


def test_rejects_schema_drift_even_when_dataset_id_matches() -> None:
    drifted = schema().model_copy(
        update={
            "columns": (
                *schema().columns[:1],
                schema().columns[1].model_copy(update={"field_name": "otro_valor"}),
            )
        }
    )
    assert_code(
        PlanValidationCode.DATASET_MISMATCH,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=drifted),
    )


@pytest.mark.parametrize("operation", [QueryOperation.SUM, QueryOperation.AVG])
def test_sum_and_avg_reject_text_columns(operation: QueryOperation) -> None:
    assert_code(
        PlanValidationCode.TYPE_MISMATCH,
        lambda: validate_query_plan(
            sum_plan(
                operation=operation,
                metrics=(sum_plan().metrics[0].model_copy(update={"operation": operation}),),
            ),
            context=context(),
            schema=schema(value_type=ColumnDataType.TEXT),
        ),
    )


@pytest.mark.parametrize("risk", [PiiRiskLevel.HIGH, PiiRiskLevel.UNKNOWN])
def test_rejects_high_and_unknown_pii_before_rendering(risk: PiiRiskLevel) -> None:
    assert_code(
        PlanValidationCode.PII_BLOCKED,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=schema(value_pii=risk)),
    )


def test_medium_pii_aggregate_requires_group_count() -> None:
    validated = validate_query_plan(
        sum_plan(), context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
    )
    assert validated.include_group_count is True


def test_lookup_of_low_risk_column_is_not_blocked_by_unrelated_dataset_medium_risk() -> None:
    """T-617B-C13-D7 (pilot-025/pilot-026, golden-v2, datasets nudc-7mev/
    f5ai-gvqt): `schema.pii_risk_level` ya es el PEOR CASO de todas las
    columnas del dataset (`classify_dataset`), incluidas columnas que el
    plan nunca selecciona. Un LOOKUP que solo toca `municipio` (`low`) no
    debe bloquearse solo porque el dataset contenga OTRA columna (`valor`)
    clasificada `medium` que esta consulta no usa en absoluto."""

    lookup_plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
        ),
        filters=(
            FilterSelection(
                column=ColumnReference(column_index=0),
                operator=FilterOperator.EQ,
                values=(ScalarValue(type=ScalarType.TEXT, value="Pasto"),),
                provenance=provenance(),
            ),
        ),
        purpose="Consultar municipio",
    )

    validated = validate_query_plan(
        lookup_plan, context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
    )

    assert validated.dimensions[0].field_name == "municipio"
    # T-617B-C13-D7 continuación: `soql_renderer` nunca agrega `group by`
    # para LOOKUP -- si `include_group_count` quedara en True aquí, el SoQL
    # renderizado mezclaría `count(*)` sin agrupar (SQL inválido, hallazgo
    # real contra Socrata: `query.soql.column-not-in-group-bys`).
    assert validated.include_group_count is False


def test_lookup_of_medium_risk_column_itself_still_requires_aggregation() -> None:
    """El acotamiento nunca deja pasar una columna MEDIUM que sí se
    selecciona -- solo deja de bloquear por columnas ajenas no consultadas."""

    lookup_plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        purpose="Consultar valor",
    )

    assert_code(
        PlanValidationCode.PII_REQUIRES_AGGREGATION,
        lambda: validate_query_plan(
            lookup_plan, context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
        ),
    )


def test_validated_plan_is_a_distinct_frozen_type() -> None:
    validated = validate_query_plan(sum_plan(), context=context(), schema=schema())
    with pytest.raises(ValidationError):
        validated.limit = 2  # type: ignore[misc]


def test_rejects_invalid_typed_literal_before_renderer() -> None:
    date_context = context().model_copy(
        update={
            "candidates": (
                context()
                .candidates[0]
                .model_copy(
                    update={
                        "columns": (
                            context()
                            .candidates[0]
                            .columns[0]
                            .model_copy(update={"data_type": ColumnDataType.DATE}),
                            context().candidates[0].columns[1],
                        )
                    }
                ),
            )
        }
    )
    date_schema = schema().model_copy(
        update={
            "columns": (
                schema().columns[0].model_copy(update={"data_type": ColumnDataType.DATE}),
                schema().columns[1],
            )
        }
    )
    invalid_plan = sum_plan().model_copy(
        update={
            "filters": (
                sum_plan()
                .filters[0]
                .model_copy(update={"values": (ScalarValue(type=ScalarType.DATE, value="2025"),)}),
            )
        }
    )
    assert_code(
        PlanValidationCode.INVALID_LITERAL,
        lambda: validate_query_plan(
            invalid_plan,
            context=date_context,
            schema=date_schema,
        ),
    )


# --- T-617B-C13-D10 (golden-v2, pilot-042-disposicion-final): un LOOKUP no --
# puede responder "código NUSD" con otro código administrativo de la misma
# familia (nuap) ni con una columna de fecha. DIVIPOLA admite evidencia
# estructural porque es el único sistema territorial que este código ya
# modela de forma dedicada, no una lista de excepciones por acrónimo.


def test_named_output_system_extracts_all_caps_token_after_codigo() -> None:
    assert (
        named_output_system("¿Qué código NUSD corresponde a la empresa 82, SOCIEDAD DE ACUEDUCTO?")
        == "NUSD"
    )
    assert named_output_system("¿Cuál es el código DIVIPOLA municipal de Medellín?") == "DIVIPOLA"
    assert (
        named_output_system("¿Qué códigos DIVIPOLA departamental y municipal corresponden?")
        == "DIVIPOLA"
    )


def test_named_output_system_ignores_generic_lowercase_wording() -> None:
    """ "código tiene"/"código de municipio"/"códigos postales": el token
    que sigue a "código" no está en mayúsculas -- no es el nombre de un
    sistema específico, es fraseo genérico. Falso positivo real evitado:
    "tiene" (verbo) casi nunca respalda ninguna columna."""

    assert named_output_system("¿Qué código tiene la entidad territorial certificada?") is None
    assert named_output_system("¿Qué código de municipio corresponde a Abriaquí?") is None
    assert named_output_system("¿Qué códigos postales publica la fuente?") is None
    assert named_output_system("¿Qué código departamental corresponde a Antioquia?") is None


def test_column_satisfies_named_output_system_requires_literal_match_for_generic_system() -> None:
    """ "NUSD" no se satisface con "nuap" (otro código administrativo de la
    misma familia) ni con una columna de fecha -- exige respaldo léxico
    explícito del propio acrónimo."""

    assert not column_satisfies_named_output_system("NUSD", field_name="nuap", display_name="NUAP")
    assert not column_satisfies_named_output_system(
        "NUSD", field_name="a_o_del_cargue", display_name="AÑO DEL CARGUE"
    )
    assert column_satisfies_named_output_system("NUSD", field_name="nusd", display_name="NUSD")


def test_column_satisfies_named_output_system_accepts_divipola_structural_evidence() -> None:
    """pilot-020-divipola (`gdxc-w37w`): `cod_dpto`/`cod_mpio` nunca
    deletrean "divipola" pero SÍ son código departamental/municipal --
    evidencia estructural suficiente."""

    assert column_satisfies_named_output_system(
        "DIVIPOLA", field_name="cod_mpio", display_name="Código Municipio"
    )
    assert column_satisfies_named_output_system(
        "DIVIPOLA", field_name="cod_dpto", display_name="Código Departamento"
    )


def test_column_satisfies_named_output_system_accepts_divipola_abbreviated_evidence() -> None:
    """pilot-023-eva-agricultura (`2pnw-mmge`): `c_d_dep`/`c_d_mun` con
    display_name "CÓD. DEP."/"CÓD. MUN." -- misma evidencia estructural con
    abreviaturas reales del catálogo, sin necesitar la palabra "divipola"."""

    assert column_satisfies_named_output_system(
        "DIVIPOLA", field_name="c_d_dep", display_name="CÓD. DEP."
    )
    assert column_satisfies_named_output_system(
        "DIVIPOLA", field_name="c_d_mun", display_name="CÓD. MUN."
    )


def test_column_satisfies_named_output_system_rejects_non_territorial_divipola_claim() -> None:
    """Una columna que no es ni código ni territorial no satisface DIVIPOLA
    por más que la pregunta lo nombre."""

    assert not column_satisfies_named_output_system(
        "DIVIPOLA", field_name="nombre_empresa", display_name="Nombre Empresa"
    )


def _named_system_context(
    *, field_name: str, display_name: str, data_type: ColumnDataType = ColumnDataType.NUMBER
) -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="abcd-1234",
                title="Dataset de prueba",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name=field_name,
                        display_name=display_name,
                        data_type=data_type,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="valor",
                        display_name="Valor",
                        data_type=ColumnDataType.NUMBER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )


def _named_system_schema(
    *, field_name: str, data_type: ColumnDataType = ColumnDataType.NUMBER
) -> ObservedDatasetSchema:
    return ObservedDatasetSchema(
        dataset_id="abcd-1234",
        eligibility_status=EligibilityStatus.ELIGIBLE,
        pii_risk_level=PiiRiskLevel.LOW,
        columns=(
            ObservedColumn(
                field_name=field_name, data_type=data_type, pii_risk_level=PiiRiskLevel.LOW
            ),
            ObservedColumn(
                field_name="valor", data_type=ColumnDataType.NUMBER, pii_risk_level=PiiRiskLevel.LOW
            ),
        ),
    )


def _named_system_lookup_plan() -> QueryPlan:
    return QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
        ),
        purpose="lookup: sistema nombrado",
    )


def test_validate_requested_output_semantics_rejects_unrelated_code_column() -> None:
    """Reproduce pilot-042-disposicion-final contra `d7pt-p5fi`: la pregunta
    nombra "código NUSD" pero la única columna de salida seleccionada es
    "nuap" (otro código administrativo) -- se rechaza el candidato."""

    validated = validate_query_plan(
        _named_system_lookup_plan(),
        context=_named_system_context(field_name="nuap", display_name="NUAP"),
        schema=_named_system_schema(field_name="nuap"),
    )
    assert_code(
        PlanValidationCode.REQUESTED_OUTPUT_SEMANTICS_MISMATCH,
        lambda: validate_requested_output_semantics(
            validated,
            context=_named_system_context(field_name="nuap", display_name="NUAP"),
            question=("¿Qué código NUSD corresponde a la empresa 82, SOCIEDAD DE ACUEDUCTO?"),
        ),
    )


def test_validate_requested_output_semantics_accepts_literal_match() -> None:
    """Reproduce el dataset correcto (`84tn-nnhf`): la columna seleccionada
    literalmente se llama "nusd" -- el plan se acepta."""

    validated = validate_query_plan(
        _named_system_lookup_plan(),
        context=_named_system_context(field_name="nusd", display_name="NUSD"),
        schema=_named_system_schema(field_name="nusd"),
    )
    validate_requested_output_semantics(
        validated,
        context=_named_system_context(field_name="nusd", display_name="NUSD"),
        question="¿Qué código NUSD corresponde a la empresa 82, SOCIEDAD DE ACUEDUCTO?",
    )


def test_validate_requested_output_semantics_accepts_divipola_structural_evidence() -> None:
    """Reproduce pilot-020-divipola (`gdxc-w37w`): la columna seleccionada
    es `cod_mpio`, sin la palabra "divipola" en ningún metadato -- se
    acepta por evidencia estructural."""

    validated = validate_query_plan(
        _named_system_lookup_plan(),
        context=_named_system_context(field_name="cod_mpio", display_name="Código Municipio"),
        schema=_named_system_schema(field_name="cod_mpio"),
    )
    validate_requested_output_semantics(
        validated,
        context=_named_system_context(field_name="cod_mpio", display_name="Código Municipio"),
        question="¿Cuál es el código DIVIPOLA municipal de Medellín (Antioquia)?",
    )


def test_validate_requested_output_semantics_accepts_divipola_abbreviated_evidence() -> None:
    """Reproduce pilot-023-eva-agricultura (`2pnw-mmge`): columnas
    abreviadas `c_d_dep`/`c_d_mun` sin la palabra "divipola" en ningún
    metadato -- se acepta por evidencia estructural."""

    validated = validate_query_plan(
        _named_system_lookup_plan(),
        context=_named_system_context(field_name="c_d_mun", display_name="CÓD. MUN."),
        schema=_named_system_schema(field_name="c_d_mun"),
    )
    validate_requested_output_semantics(
        validated,
        context=_named_system_context(field_name="c_d_mun", display_name="CÓD. MUN."),
        question=(
            "¿Qué códigos DIVIPOLA departamental y municipal corresponden a Busbanzá, Boyacá?"
        ),
    )


def test_validate_requested_output_semantics_ignores_questions_without_named_system() -> None:
    """Control: sin el patrón "código <ACRÓNIMO>", la validación nunca se
    activa -- ningún caso existente sin este fraseo puede verse afectado."""

    validated = validate_query_plan(sum_plan(), context=context(), schema=schema())
    validate_requested_output_semantics(
        validated,
        context=context(),
        question="¿Cuál es el total por municipio en Pasto?",
    )
