import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agent.llm_contracts import (
    CandidateRanking,
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    MetricChoice,
    SortChoice,
    ground_intent_topic_in_question,
    materialize_query_plan,
    normalize_aggregate_intent,
    normalize_budget_snapshot,
    normalize_direct_quantity_lookup,
    normalize_explicit_date_filter,
    normalize_intent_for_observed_schema,
    normalize_lookup_filters,
    normalize_lookup_output_columns,
    normalize_ranked_aggregate,
    normalize_sort_references,
    normalize_source_observation_cutoff_filters,
    normalize_system_owned_operation,
    normalize_temporal_year_filters,
    validate_candidate_ranking,
    validate_grounded_synthesis,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    DatasetOption,
    EnumeratedPlanningContext,
    FilterOperator,
    PiiRiskLevel,
    QueryOperation,
    ScalarType,
    SelectionOrigin,
    SortDirection,
    SortTargetKind,
)
from app.quality.claims import BuiltClaim


def context() -> EnumeratedPlanningContext:
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
                        field_name="municipio",
                        display_name="Municipio",
                        data_type=ColumnDataType.TEXT,
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


def intent(operation: QueryOperation = QueryOperation.SUM) -> IntentExtraction:
    return IntentExtraction(
        topic="homicidios por departamento",
        operation=operation,
        territory="Colombia",
        administrative_terms=("departamento", "seguridad ciudadana"),
    )


def test_llm_schemas_do_not_expose_free_identifiers_or_soql() -> None:
    schemas = (
        IntentExtraction.model_json_schema(),
        CandidateRanking.model_json_schema(),
        EnumeratedPlanSelection.model_json_schema(),
    )
    serialized = json.dumps(schemas).casefold()
    for forbidden in ("dataset_id", "field_name", "evidence_id", "soql", "where_clause"):
        assert forbidden not in serialized


def test_candidate_ranking_only_accepts_unique_existing_indexes() -> None:
    ranking = CandidateRanking(ranked_candidate_indexes=(0,))
    validate_candidate_ranking(ranking, context())
    with pytest.raises(ValidationError, match="duplicados"):
        CandidateRanking(ranked_candidate_indexes=(0, 0))
    with pytest.raises(ValueError, match="inexistentes"):
        validate_candidate_ranking(CandidateRanking(ranked_candidate_indexes=(1,)), context())


def test_materializes_query_plan_with_system_owned_provenance() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(0,),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Pasto",),
            ),
        ),
        limit=10,
    )
    plan = materialize_query_plan(selection, intent=intent(), context=context())
    assert plan.dataset_index == 0
    assert plan.dimensions[0].column.column_index == 0
    assert plan.metrics[0].column is not None
    assert plan.metrics[0].column.column_index == 1
    assert plan.metrics[0].provenance.origin is SelectionOrigin.INTENT


def test_lookup_keeps_filter_whose_value_is_literal_in_question() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        filters=(
            FilterChoice(
                column_index=1,
                operator=FilterOperator.EQ,
                value_type=ScalarType.NUMBER,
                values=("2024",),
            ),
        ),
    )

    normalized = normalize_lookup_filters(
        selection,
        question="¿Qué valor aparece en 2024?",
        context=context(),
    )

    assert normalized.filters == selection.filters


def test_lookup_discards_ungrounded_filter_on_arbitrary_column() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        filters=(
            FilterChoice(
                column_index=1,
                operator=FilterOperator.EQ,
                value_type=ScalarType.NUMBER,
                values=("999",),
            ),
        ),
    )

    normalized = normalize_lookup_filters(
        selection,
        question="¿Qué valor aparece en un registro?",
        context=context(),
    )

    assert normalized.filters == ()


def test_explicit_spanish_date_becomes_datetime_day_range() -> None:
    date_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="date-1234",
                title="Observaciones",
                publisher="IDEAM",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="codigoestacion",
                        display_name="Código estación",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="fechaobservacion",
                        display_name="Fecha observación",
                        data_type=ColumnDataType.DATETIME,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )
    selection = EnumeratedPlanSelection(dataset_index=0, operation=QueryOperation.LOOKUP)

    normalized = normalize_explicit_date_filter(
        selection,
        question="¿Qué estación registró una observación el 11 de febrero de 2019?",
        context=date_context,
    )

    assert normalized.filters[0].column_index == 1
    assert normalized.filters[0].operator is FilterOperator.GTE
    assert normalized.filters[1].operator is FilterOperator.LT
    assert normalized.filters[0].value_type is ScalarType.DATETIME
    assert normalized.filters[0].values == ("2019-02-11T00:00:00",)
    assert normalized.filters[1].values == ("2019-02-12T00:00:00",)


def _period_context() -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="peri-1234",
                title="Eventos por periodo",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="ano",
                        display_name="Año",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="semana",
                        display_name="Semana",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=2,
                        field_name="conteo",
                        display_name="Conteo",
                        data_type=ColumnDataType.NUMBER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )


def test_source_observation_date_is_not_materialized_as_row_period() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=2),),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.INTEGER,
                values=("2024",),
            ),
            FilterChoice(
                column_index=1,
                operator=FilterOperator.LTE,
                value_type=ScalarType.INTEGER,
                values=("42",),
            ),
        ),
    )

    normalized = normalize_source_observation_cutoff_filters(
        selection,
        question=(
            "¿Qué evento tuvo mayor volumen acumulado en la fuente observada "
            "al 17 de octubre de 2024?"
        ),
        context=_period_context(),
    )

    assert normalized.filters == ()


def test_explicit_period_outside_source_cutoff_clause_is_preserved() -> None:
    year_filter = FilterChoice(
        column_index=0,
        operator=FilterOperator.EQ,
        value_type=ScalarType.INTEGER,
        values=("2024",),
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=2),),
        filters=(year_filter,),
    )

    normalized = normalize_source_observation_cutoff_filters(
        selection,
        question=(
            "¿Cuál fue el total durante 2024 según la fuente observada al 17 de octubre de 2024?"
        ),
        context=_period_context(),
    )

    assert normalized.filters == (year_filter,)


def test_plain_user_date_keeps_normal_date_filter_semantics() -> None:
    date_filter = FilterChoice(
        column_index=0,
        operator=FilterOperator.EQ,
        value_type=ScalarType.INTEGER,
        values=("2024",),
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=2),),
        filters=(date_filter,),
    )

    normalized = normalize_source_observation_cutoff_filters(
        selection,
        question="¿Cuál fue el total al 17 de octubre de 2024?",
        context=_period_context(),
    )

    assert normalized.filters == (date_filter,)


def test_materialization_rejects_invented_column_index() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(99,),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
    )
    with pytest.raises(ValueError, match="column_index inexistente"):
        materialize_query_plan(selection, intent=intent(), context=context())


def test_materialization_rejects_operation_different_from_intent() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.COUNT,
        metrics=(MetricChoice(operation=QueryOperation.COUNT),),
    )
    with pytest.raises(ValueError, match="debe coincidir"):
        materialize_query_plan(
            selection,
            intent=intent(QueryOperation.SUM),
            context=context(),
        )


def _entity_context() -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="ent1-2345",
                title="Planta de personal",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="nombre_de_la_entidad",
                        display_name="Nombre de la entidad",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="genero_hombre",
                        display_name="Género hombre",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=2,
                        field_name="mes",
                        display_name="Mes",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )


def _entity_intent(entity: str | None) -> IntentExtraction:
    return IntentExtraction(
        topic="composición por sexo de la planta",
        operation=QueryOperation.LOOKUP,
        entity=entity,
    )


def _entity_identifier_context() -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="proj-1234",
                title="Proyectos APP",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="codigo",
                        display_name="Código",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="nombre_entidad",
                        display_name="Nombre entidad",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=2,
                        field_name="nombre_proyecto",
                        display_name="Nombre proyecto",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )


def test_materialization_rejects_plan_that_omits_explicit_entity_filter() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    with pytest.raises(ValueError, match="omite la restricción de entidad"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=_entity_context(),
        )


def test_materialization_accepts_plan_with_equivalent_entity_filter() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("MINISTERIO DE RELACIONES EXTERIORES",),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Ministerio de Relaciones Exteriores"),
        context=_entity_context(),
    )
    assert plan.filters[0].column.column_index == 0


def test_materialization_accepts_specific_entity_identifier_filter() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(2,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("PRY00062",),
            ),
        ),
        limit=1,
    )

    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("APP PRY00062"),
        context=_entity_identifier_context(),
    )

    assert plan.filters[0].column.column_index == 0


def test_identifier_filter_does_not_replace_unrelated_institution_filter() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("PRY00062",),
            ),
        ),
        limit=1,
    )

    with pytest.raises(ValueError, match="entidad solicitada"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=_entity_identifier_context(),
        )


def test_unrelated_identifier_column_does_not_block_grounded_place_filter() -> None:
    """Una columna ``codigo`` no convierte un municipio en identificador.

    La protección R5 debe impedir perder una entidad institucional o un código
    explícito; no debe rechazar un filtro territorial correcto solo porque el
    mismo dataset también publique una columna auxiliar de código.
    """

    context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="plac-1234",
                title="Indicadores municipales",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="codigo",
                        display_name="Código",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="nombre_empresa",
                        display_name="Nombre empresa",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=2,
                        field_name="municipio",
                        display_name="Municipio",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=3,
                        field_name="cantidad",
                        display_name="Cantidad",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1, 2, 3),
        filters=(
            FilterChoice(
                column_index=2,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("VILLAMARÍA",),
            ),
        ),
        limit=1,
    )

    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Villamaría"),
        context=context,
    )

    assert plan.filters[0].column.column_index == 2


def test_explicit_identifier_still_requires_identifier_filter() -> None:
    """Un identificador alfanumérico explícito no puede perderse del plan."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(2,),
        limit=1,
    )

    with pytest.raises(ValueError, match="omite la restricción de entidad"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("APP PRY00062"),
            context=_entity_identifier_context(),
        )


def test_materialization_rejects_plan_that_contradicts_entity_filter() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("INPEC",),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    with pytest.raises(ValueError, match="entidad solicitada"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=_entity_context(),
        )


def test_materialization_does_not_require_entity_filter_when_intent_has_no_entity() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent(None),
        context=_entity_context(),
    )
    assert plan.filters == ()


def test_materialization_does_not_block_suboptimal_temporal_selection_with_entity() -> None:
    """Una selección temporal mejorable (sin filtro de mes) no debe bloquearse:
    esta corrección solo protege la entidad, no la optimalidad del periodo."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1, 2),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Ministerio de Relaciones Exteriores",),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=1),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Ministerio de Relaciones Exteriores"),
        context=_entity_context(),
    )
    assert len(plan.filters) == 1


def test_materialization_rejects_in_filter_mixing_correct_and_other_entity() -> None:
    """R5A: un valor coincidente no basta si la lista IN incluye otra entidad."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.IN,
                value_type=ScalarType.TEXT,
                values=("Ministerio de Relaciones Exteriores", "INPEC"),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    with pytest.raises(ValueError, match="entidad solicitada"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=_entity_context(),
        )


def test_materialization_accepts_in_filter_with_only_equivalent_entity_variants() -> None:
    """R5A: un IN cuyos valores son todos variantes de la misma entidad sí es válido."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.IN,
                value_type=ScalarType.TEXT,
                values=(
                    "Ministerio de Relaciones Exteriores",
                    "MINISTERIO DE RELACIONES EXTERIORES",
                ),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Ministerio de Relaciones Exteriores"),
        context=_entity_context(),
    )
    assert plan.filters[0].column.column_index == 0


def test_materialization_rejects_single_generic_word_as_entity_equivalence() -> None:
    """R5A: 'Ministerio' solo no equivale a 'Ministerio de Relaciones Exteriores'."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Ministerio",),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    with pytest.raises(ValueError, match="entidad solicitada"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=_entity_context(),
        )


def test_materialization_accepts_sufficiently_specific_normalized_variant() -> None:
    """R5A: una forma más específica y normalizada de la misma entidad sí se acepta."""

    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Ministerio de Relaciones Exteriores de Colombia",),
            ),
        ),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Ministerio de Relaciones Exteriores"),
        context=_entity_context(),
    )
    assert plan.filters[0].column.column_index == 0


def test_product_name_column_is_not_classified_as_institutional_entity() -> None:
    """R5A: 'nombre_producto' no debe activar la protección de entidad."""

    product_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="prod-1234",
                title="Catálogo de productos",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="nombre_producto",
                        display_name="Nombre del producto",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="cantidad",
                        display_name="Cantidad",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    plan = materialize_query_plan(
        selection,
        intent=_entity_intent("Ministerio de Relaciones Exteriores"),
        context=product_context,
    )
    assert plan.filters == ()


def test_institutional_name_columns_are_recognized_as_entity_columns() -> None:
    """R5A: 'nombre_de_la_entidad' y 'nombre_empresa' sí cuentan como columna de entidad."""

    institutional_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="inst-1234",
                title="Directorio institucional",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="nombre_de_la_entidad",
                        display_name="Nombre de la entidad",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="nombre_empresa",
                        display_name="Nombre empresa",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=2,
                        field_name="valor",
                        display_name="Valor",
                        data_type=ColumnDataType.INTEGER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(2,),
        order_by=(SortChoice(target_kind=SortTargetKind.DIMENSION, target_index=0),),
        limit=1,
    )
    with pytest.raises(ValueError, match="omite la restricción de entidad"):
        materialize_query_plan(
            selection,
            intent=_entity_intent("Ministerio de Relaciones Exteriores"),
            context=institutional_context,
        )


def test_structured_outputs_forbid_extra_free_text_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        EnumeratedPlanSelection.model_validate(
            {
                "dataset_index": 0,
                "operation": "sum",
                "metrics": [{"operation": "sum", "column_index": 1}],
                "soql": "select sum(valor)",
            }
        )


def test_textual_extension_discards_only_free_text_items_without_interpreting_them() -> None:
    selection = EnumeratedPlanSelection.model_validate(
        {
            "dataset_index": 0,
            "operation": "sum",
            "metrics": [{"operation": "sum", "column_index": 1}],
            "textual_requests": [
                "No se puede determinar el texto solicitado.",
                {
                    "operation": "direct_text",
                    "source_row_indexes": [0],
                    "column": {"column_index": 2},
                },
            ],
        }
    )

    assert len(selection.textual_requests) == 1
    assert selection.textual_requests[0].operation.value == "direct_text"
    assert selection.textual_requests[0].column.column_index == 2


def test_lookup_metrics_with_only_integral_indexes_become_dimensions() -> None:
    selection = EnumeratedPlanSelection.model_validate(
        {
            "dataset_index": 0,
            "operation": "lookup",
            "dimension_column_indexes": [1],
            "metrics": [
                {"operation": "lookup", "column_index": 19.0},
                {"operation": "lookup", "column_index": 20},
                {"operation": "lookup", "column_index": 21.0},
            ],
        }
    )

    assert selection.dimension_column_indexes == (1, 19, 20, 21)
    assert selection.metrics == ()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "dataset_index": 0,
            "operation": "sum",
            "metrics": [{"operation": "sum", "column_index": 1}],
            "textual_requests": "explicación libre fuera de una lista",
        },
        {
            "dataset_index": 0,
            "operation": "sum",
            "metrics": [{"operation": "sum", "column_index": 1}],
            "textual_requests": [
                {
                    "operation": "direct_text",
                    "source_row_indexes": [0],
                    "column": {"column_index": 2},
                    "texto_inventado": "no permitido",
                }
            ],
        },
        {
            "dataset_index": 0,
            "operation": "lookup",
            "metrics": [{"operation": "lookup", "column_index": 2, "explanation": "no"}],
        },
        {
            "dataset_index": 0,
            "operation": "sum",
            "metrics": [{"operation": "lookup", "column_index": 2}],
        },
    ],
)
def test_optional_shape_recovery_keeps_all_other_invalid_outputs_strict(payload: dict) -> None:
    with pytest.raises(ValidationError):
        EnumeratedPlanSelection.model_validate(payload)


def test_count_cannot_choose_a_column_and_lookup_is_not_a_metric() -> None:
    with pytest.raises(ValidationError, match=r"count\(\*\)"):
        MetricChoice(operation=QueryOperation.COUNT, column_index=1)
    with pytest.raises(ValidationError, match="lookup"):
        MetricChoice(operation=QueryOperation.LOOKUP, column_index=1)


def _claim(display_value: str = "66.723") -> BuiltClaim:
    return BuiltClaim(
        claim_type="direct",
        description="Total",
        raw_value=Decimal("66723"),
        display_value=display_value,
        unit=None,
        rounding=0,
        formula=None,
        source_row_indexes=(0,),
        columns_used=("metric_0",),
        source_hash="sha256:test",
    )


def test_grounded_synthesis_accepts_only_existing_claims_and_supported_figures() -> None:
    synthesis = GroundedSynthesis(
        answer="El total observado fue 66.723.",
        cited_claim_indexes=(0,),
    )
    validate_grounded_synthesis(synthesis, (_claim(),))

    with pytest.raises(ValueError, match="inexistentes"):
        validate_grounded_synthesis(
            GroundedSynthesis(answer="Resultado disponible.", cited_claim_indexes=(1,)),
            (_claim(),),
        )


def _labeled_claim(display_value: str, label: str, label_status: str = "verified") -> BuiltClaim:
    return BuiltClaim(
        claim_type="direct",
        description="Total",
        raw_value=Decimal(display_value.replace(".", "").replace(",", "")),
        display_value=display_value,
        unit=None,
        rounding=0,
        formula=None,
        source_row_indexes=(0,),
        columns_used=("dim_1",),
        source_hash="sha256:test",
        public_columns=("columna_real",),
        label=label,
        label_status=label_status,
    )


def test_grounded_synthesis_accepts_verified_label_next_to_its_own_value() -> None:
    claim = _labeled_claim("764", "Hombres")
    synthesis = GroundedSynthesis(
        answer="La planta está compuesta por Hombres: 764.",
        cited_claim_indexes=(0,),
    )
    validate_grounded_synthesis(synthesis, (claim,))


def test_grounded_synthesis_rejects_swapped_label_between_two_cited_claims() -> None:
    """RF-212: no debe bastar con que la etiqueta y la cifra existan en el
    texto en cualquier parte; deben corresponder al MISMO claim citado."""

    hombres = _labeled_claim("764", "Hombres")
    mujeres = _labeled_claim("719", "Mujeres")
    swapped_answer = (
        "En la categoría reportada como Mujeres se observó un total "
        "consolidado que asciende a 764, mientras que en la categoría "
        "identificada por separado como Hombres el resultado fue distinto: "
        "solamente 719."
    )
    synthesis = GroundedSynthesis(answer=swapped_answer, cited_claim_indexes=(0, 1))
    with pytest.raises(ValueError, match="no asocia la etiqueta"):
        validate_grounded_synthesis(synthesis, (hombres, mujeres))


def test_grounded_synthesis_skips_label_check_for_ambiguous_claims() -> None:
    ambiguous = BuiltClaim(
        claim_type="derived",
        description="Tasa",
        raw_value=Decimal("8.4"),
        display_value="8,4 %",
        unit="%",
        rounding=1,
        formula={"op": "div", "args": [{"col": "a"}, {"col": "b"}]},
        source_row_indexes=(0,),
        columns_used=("dim_1", "dim_2"),
        source_hash="sha256:test",
        public_columns=("columna_a", "columna_b"),
        label=None,
        label_status="ambiguous",
    )
    synthesis = GroundedSynthesis(
        answer="Resultado observado: 8,4 % (sin etiqueta verificable).",
        cited_claim_indexes=(0,),
    )
    validate_grounded_synthesis(synthesis, (ambiguous,))


def test_normalizes_explicit_year_only_for_observed_temporal_column() -> None:
    temporal_context = context().model_copy(
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
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.COUNT,
        metrics=(MetricChoice(operation=QueryOperation.COUNT),),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.DATE,
                values=("2025",),
            ),
        ),
    )
    normalized = normalize_temporal_year_filters(selection, temporal_context)
    assert normalized.filters[0].operator is FilterOperator.BETWEEN
    assert normalized.filters[0].values == ("2025-01-01", "2025-12-31")


def test_count_operation_is_owned_by_system_and_always_becomes_count_star() -> None:
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
    )
    normalized = normalize_system_owned_operation(
        proposed,
        intent(QueryOperation.COUNT),
    )
    assert normalized.operation is QueryOperation.COUNT
    assert normalized.metrics == (MetricChoice(operation=QueryOperation.COUNT),)


def _quantity_context(*columns: tuple[str, str, ColumnDataType]) -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="qty1-2345",
                title="Indicadores publicados",
                publisher="Entidad oficial",
                columns=tuple(
                    ColumnOption(
                        index=index,
                        field_name=field_name,
                        display_name=display_name,
                        data_type=data_type,
                        pii_risk_level=PiiRiskLevel.LOW,
                    )
                    for index, (field_name, display_name, data_type) in enumerate(columns)
                ),
            ),
        )
    )


@pytest.mark.parametrize(
    ("question", "columns", "expected_index"),
    [
        (
            "¿Cuántos hallazgos administrativos se reportaron en 2019?",
            (
                ("vigencia", "Vigencia", ColumnDataType.INTEGER),
                (
                    "hallazgos_administrativos",
                    "Hallazgos administrativos",
                    ColumnDataType.INTEGER,
                ),
            ),
            1,
        ),
        (
            "¿Cuántas personas socializadas se reportaron en enero?",
            (
                ("a_o", "Año", ColumnDataType.INTEGER),
                ("cantidad", "Cantidad", ColumnDataType.INTEGER),
            ),
            1,
        ),
    ],
)
def test_count_question_uses_published_numeric_measure_instead_of_counting_rows(
    question: str,
    columns: tuple[tuple[str, str, ColumnDataType], ...],
    expected_index: int,
) -> None:
    observed = _quantity_context(*columns)
    normalized_intent = normalize_intent_for_observed_schema(
        intent(QueryOperation.COUNT),
        question=question,
        context=observed,
    )
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.COUNT,
        metrics=(MetricChoice(operation=QueryOperation.COUNT),),
    )
    normalized_selection = normalize_system_owned_operation(proposed, normalized_intent)
    normalized_selection = normalize_direct_quantity_lookup(
        normalized_selection,
        question=question,
        context=observed,
    )

    assert normalized_intent.operation is QueryOperation.LOOKUP
    assert normalized_selection.operation is QueryOperation.LOOKUP
    assert normalized_selection.metrics == ()
    assert expected_index in normalized_selection.dimension_column_indexes


def test_explicit_record_cardinality_remains_count_star() -> None:
    question = "¿Cuántos registros existen para 2019?"
    observed = _quantity_context(
        ("vigencia", "Vigencia", ColumnDataType.INTEGER),
        ("cantidad", "Cantidad", ColumnDataType.INTEGER),
    )

    normalized = normalize_intent_for_observed_schema(
        intent(QueryOperation.COUNT),
        question=question,
        context=observed,
    )

    assert normalized.operation is QueryOperation.COUNT


def test_ambiguous_published_quantities_do_not_replace_count() -> None:
    question = "¿Cuántas personas se reportaron?"
    observed = _quantity_context(
        ("cantidad_hombres", "Cantidad hombres", ColumnDataType.INTEGER),
        ("cantidad_mujeres", "Cantidad mujeres", ColumnDataType.INTEGER),
    )

    normalized = normalize_intent_for_observed_schema(
        intent(QueryOperation.COUNT),
        question=question,
        context=observed,
    )

    assert normalized.operation is QueryOperation.COUNT


@pytest.mark.parametrize(
    ("question", "columns"),
    [
        (
            "¿Cuántos puestos de votación se habilitaron para las elecciones?",
            (
                ("cantidad_elecciones", "Cantidad elecciones", ColumnDataType.INTEGER),
                ("puesto", "Puesto", ColumnDataType.TEXT),
            ),
        ),
        (
            "¿Qué administrador, número de calzadas y categoría se registran?",
            (
                (
                    "grupo_administrador_vial",
                    "Grupo administrador vial",
                    ColumnDataType.INTEGER,
                ),
                ("numero_calzadas", "Número de calzadas", ColumnDataType.INTEGER),
            ),
        ),
    ],
)
def test_unrelated_numeric_columns_do_not_replace_count(
    question: str,
    columns: tuple[tuple[str, str, ColumnDataType], ...],
) -> None:
    normalized = normalize_intent_for_observed_schema(
        intent(QueryOperation.COUNT),
        question=question,
        context=_quantity_context(*columns),
    )

    assert normalized.operation is QueryOperation.COUNT


def test_observed_institutional_schema_recovers_missing_entity_from_grounded_term() -> None:
    observed = _quantity_context(
        ("sujeto_auditado", "Sujeto auditado", ColumnDataType.TEXT),
        ("hallazgos_administrativos", "Hallazgos administrativos", ColumnDataType.INTEGER),
    )
    extracted = IntentExtraction(
        topic="hallazgos administrativos",
        operation=QueryOperation.COUNT,
        administrative_terms=(
            "administrativos",
            "auditoría regular",
            "Contraloría General de Antioquia",
        ),
    )

    normalized = normalize_intent_for_observed_schema(
        extracted,
        question=(
            "¿Cuántos hallazgos administrativos reportó la auditoría regular "
            "a la Contraloría General de Antioquia?"
        ),
        context=observed,
    )

    assert normalized.entity == "Contraloría General de Antioquia"


def test_recovered_entity_requires_subject_filter_during_materialization() -> None:
    observed = _quantity_context(
        ("sujeto_auditado", "Sujeto auditado", ColumnDataType.TEXT),
        ("hallazgos_administrativos", "Hallazgos administrativos", ColumnDataType.INTEGER),
    )
    extracted = IntentExtraction(
        topic="hallazgos administrativos",
        operation=QueryOperation.COUNT,
        administrative_terms=("Contraloría General de Antioquia",),
    )
    normalized = normalize_intent_for_observed_schema(
        extracted,
        question=(
            "¿Cuántos hallazgos administrativos reportó la Contraloría General de Antioquia?"
        ),
        context=observed,
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(1,),
        limit=1,
    )

    with pytest.raises(ValueError, match="omite la restricción de entidad"):
        materialize_query_plan(selection, intent=normalized, context=observed)


def test_missing_entity_is_not_inferred_without_institutional_schema() -> None:
    extracted = IntentExtraction(
        topic="cantidad de productos",
        operation=QueryOperation.COUNT,
        administrative_terms=("Ministerio de ejemplo",),
    )

    normalized = normalize_intent_for_observed_schema(
        extracted,
        question="¿Cuántos productos dicen Ministerio de ejemplo?",
        context=_quantity_context(
            ("nombre_producto", "Nombre producto", ColumnDataType.TEXT),
            ("cantidad", "Cantidad", ColumnDataType.INTEGER),
        ),
    )

    assert normalized.entity is None


def test_lookup_preserves_metric_columns_as_enumerated_output_dimensions() -> None:
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(0,),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
    )
    normalized = normalize_system_owned_operation(
        proposed,
        intent(QueryOperation.LOOKUP),
    )
    assert normalized.operation is QueryOperation.LOOKUP
    assert normalized.metrics == ()
    assert normalized.dimension_column_indexes == (0, 1)
    with pytest.raises(ValueError, match="huérfanas"):
        validate_grounded_synthesis(
            GroundedSynthesis(answer="El total fue 99.999.", cited_claim_indexes=(0,)),
            (_claim(),),
        )


def test_lookup_prioritizes_exact_indicator_over_generic_unit_columns() -> None:
    lookup_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="d7pt-p5fi",
                title="Residuos",
                publisher="SSPD",
                columns=tuple(
                    ColumnOption(
                        index=index,
                        field_name=name,
                        display_name=name,
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    )
                    for index, name in enumerate(
                        (
                            "municipio_rea_de_prestaci",
                            "a_o_del_cargue",
                            "nombre_empresa",
                            "toneladas_de_barrido_y",
                            "toneladas_de_limpieza_urbana",
                            "toneladas_recolectadas",
                        )
                    )
                ),
            ),
        )
    )
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(0, 1, 2, 3, 4, 5),
    )

    normalized = normalize_lookup_output_columns(
        proposed,
        question="¿Qué volumen de limpieza urbana reportó Villamaría?",
        context=lookup_context,
    )

    assert normalized.dimension_column_indexes[:4] == (4, 2, 0, 1)
    assert 3 not in normalized.dimension_column_indexes


def test_latest_lookup_orders_by_year_and_month_not_indicator() -> None:
    latest_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="h8rs-jxum",
                title="Empleo público",
                publisher="DAFP",
                columns=tuple(
                    ColumnOption(
                        index=index,
                        field_name=name,
                        display_name=name,
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    )
                    for index, name in enumerate(("genero_hombre", "genero_mujer", "a_o", "mes"))
                ),
            ),
        )
    )
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        order_by=(
            SortChoice(
                target_kind=SortTargetKind.DIMENSION,
                target_index=0,
                direction=SortDirection.DESC,
            ),
        ),
    )

    normalized = normalize_lookup_output_columns(
        proposed,
        question="Composición por sexo en el último mes disponible",
        context=latest_context,
    )

    assert tuple(item.target_index for item in normalized.order_by) == (2, 3)
    assert normalized.limit == 1


def test_plant_count_lookup_prioritizes_total_and_year_over_subtypes() -> None:
    plant_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="fvq4-wwtz",
                title="Planta por entidad",
                publisher="DAFP",
                columns=tuple(
                    ColumnOption(
                        index=index,
                        field_name=name,
                        display_name=name,
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    )
                    for index, name in enumerate(
                        (
                            "nombre",
                            "no_planta_docente",
                            "no_planta_permanente",
                            "no_planta_temporal",
                            "no_total_planta",
                            "anio_aplicar",
                        )
                    )
                ),
            ),
        )
    )

    normalized = normalize_lookup_output_columns(
        EnumeratedPlanSelection(dataset_index=0, operation=QueryOperation.LOOKUP),
        question="¿Cuántos cargos de planta tiene la entidad y en qué año aplica?",
        context=plant_context,
    )

    assert normalized.dimension_column_indexes[0] == 4
    assert 5 in normalized.dimension_column_indexes
    assert 1 not in normalized.dimension_column_indexes


def test_generic_characteristics_lookup_keeps_all_columns_without_narrowing() -> None:
    """Reproduce golden-v1 pilot-022-red-vial: "¿Qué características básicas
    se registran para el tramo vial 55ST02?" solo comparte tokens léxicos
    con columnas que describen el TIPO de entidad ("tramo"/"vial"), no un
    indicador pedido -- antes de este fix, eso recortaba `calzada`/
    `categoria`, exactamente las columnas que exige `expected_fact`."""

    road_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="ie7y-asdn",
                title="Red vial",
                publisher="INVIAS",
                columns=tuple(
                    ColumnOption(
                        index=index,
                        field_name=name,
                        display_name=name,
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    )
                    for index, name in enumerate(
                        (
                            "codigo_tramo",
                            "grupo_administrador_vial",
                            "nombre_tramo",
                            "nombre_ruta",
                            "calzada",
                            "categoria",
                        )
                    )
                ),
            ),
        )
    )
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(0, 1, 2, 3),
    )

    normalized = normalize_lookup_output_columns(
        proposed,
        question="¿Qué características básicas se registran para el tramo vial 55ST02?",
        context=road_context,
    )

    assert 4 in normalized.dimension_column_indexes  # calzada
    assert 5 in normalized.dimension_column_indexes  # categoria


def test_ranked_aggregate_materializes_group_order_and_top_one() -> None:
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
    )

    normalized = normalize_ranked_aggregate(
        proposed,
        question="¿Qué municipios concentran mayor valor?",
        context=context(),
    )

    assert normalized.dimension_column_indexes == (0,)
    assert normalized.order_by == (
        SortChoice(
            target_kind=SortTargetKind.METRIC,
            target_index=0,
            direction=SortDirection.DESC,
        ),
    )
    assert normalized.limit == 1


def test_lookup_sort_column_is_added_and_converted_to_dimension_position() -> None:
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimension_column_indexes=(0,),
        order_by=(
            SortChoice(
                target_kind=SortTargetKind.DIMENSION,
                target_index=1,
                direction=SortDirection.DESC,
            ),
        ),
    )

    normalized = normalize_sort_references(proposed, context())

    assert normalized.dimension_column_indexes == (0, 1)
    assert normalized.order_by[0].target_index == 1


def test_cumulative_ranking_normalizes_intent_to_sum() -> None:
    normalized = normalize_aggregate_intent(
        intent(QueryOperation.MAX),
        "¿Qué evento tiene mayor volumen reportado?",
    )

    assert normalized.operation is QueryOperation.SUM


def test_intent_topic_preserves_literal_user_question_for_retrieval() -> None:
    proposed = intent().model_copy(update={"topic": "seguridad ciudadana"})

    normalized = ground_intent_topic_in_question(
        proposed,
        "¿Qué departamento concentra más homicidios reportados?",
    )

    assert "homicidios" in normalized.topic


def test_budget_snapshot_is_not_summed_across_periods() -> None:
    budget_context = context().model_copy(
        update={
            "candidates": (
                context()
                .candidates[0]
                .model_copy(
                    update={
                        "columns": (
                            ColumnOption(
                                index=0,
                                field_name="descripci_n",
                                display_name="Descripción",
                                data_type=ColumnDataType.TEXT,
                                pii_risk_level=PiiRiskLevel.LOW,
                            ),
                            ColumnOption(
                                index=1,
                                field_name="mes",
                                display_name="Mes",
                                data_type=ColumnDataType.TEXT,
                                pii_risk_level=PiiRiskLevel.LOW,
                            ),
                            ColumnOption(
                                index=2,
                                field_name="apropiaci_n_vigente",
                                display_name="Apropiación vigente",
                                data_type=ColumnDataType.TEXT,
                                pii_risk_level=PiiRiskLevel.LOW,
                            ),
                            ColumnOption(
                                index=3,
                                field_name="pagos",
                                display_name="Pagos",
                                data_type=ColumnDataType.TEXT,
                                pii_risk_level=PiiRiskLevel.LOW,
                            ),
                        )
                    }
                ),
            )
        }
    )
    proposed = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=3),),
    )

    normalized = normalize_budget_snapshot(
        proposed,
        question="¿Cuál fue la ejecución presupuestal y cuánto se pagó?",
        context=budget_context,
    )

    assert normalized.operation is QueryOperation.LOOKUP
    assert normalized.metrics == ()
    assert normalized.limit == 1
    assert normalized.filters[0].values == ("Funcionamiento",)
    assert normalized.order_by[0].direction is SortDirection.ASC
