"""Contratos estructurados y acotados para la participación del LLM."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DimensionSelection,
    EnumeratedPlanningContext,
    FilterOperator,
    FilterSelection,
    MetricSelection,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
    SelectionOrigin,
    SelectionProvenance,
    SortDirection,
    SortSelection,
    SortTargetKind,
    TextualSelection,
)
from app.quality.claim_labels import label_grounded_in_text
from app.quality.claims import BuiltClaim, find_orphan_figures


class _LLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentExtraction(_LLMOutput):
    topic: str = Field(min_length=1, max_length=300)
    operation: QueryOperation
    territory: str | None = Field(default=None, max_length=200)
    entity: str | None = Field(default=None, max_length=300)
    period: str | None = Field(default=None, max_length=100)
    administrative_terms: tuple[str, ...] = Field(default_factory=tuple, max_length=8)


class CandidateRanking(_LLMOutput):
    ranked_candidate_indexes: tuple[int, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _indexes_are_unique(self) -> CandidateRanking:
        if len(set(self.ranked_candidate_indexes)) != len(self.ranked_candidate_indexes):
            raise ValueError("ranked_candidate_indexes no admite duplicados")
        if any(index < 0 for index in self.ranked_candidate_indexes):
            raise ValueError("los índices de candidatos deben ser no negativos")
        return self


class MetricChoice(_LLMOutput):
    operation: QueryOperation
    column_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _shape(self) -> MetricChoice:
        if self.operation is QueryOperation.COUNT and self.column_index is not None:
            raise ValueError("count representa count(*) y no selecciona columna")
        requires_column = self.operation not in {
            QueryOperation.COUNT,
            QueryOperation.LOOKUP,
        }
        if requires_column and self.column_index is None:
            raise ValueError(f"{self.operation.value} requiere column_index")
        if self.operation is QueryOperation.LOOKUP:
            raise ValueError("lookup se representa mediante dimension_column_indexes")
        return self


class FilterChoice(_LLMOutput):
    column_index: int = Field(ge=0)
    operator: FilterOperator
    value_type: ScalarType | None = None
    values: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def _shape(self) -> FilterChoice:
        if self.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
            if self.value_type is not None or self.values:
                raise ValueError("los filtros null no aceptan tipo ni valores")
        elif self.value_type is None:
            raise ValueError("un filtro con valores requiere value_type")
        return self


class SortChoice(_LLMOutput):
    target_kind: SortTargetKind
    target_index: int = Field(ge=0)
    direction: SortDirection = SortDirection.ASC


class QuantitativePlanSelection(_LLMOutput):
    """Contrato histórico exacto usado cuando la capacidad textual está apagada."""

    dataset_index: int = Field(ge=0)
    operation: QueryOperation
    dimension_column_indexes: tuple[int, ...] = Field(default_factory=tuple, max_length=8)
    metrics: tuple[MetricChoice, ...] = Field(default_factory=tuple, max_length=8)
    filters: tuple[FilterChoice, ...] = Field(default_factory=tuple, max_length=16)
    order_by: tuple[SortChoice, ...] = Field(default_factory=tuple, max_length=8)
    limit: int = Field(default=100, ge=1, le=5000)
    needs_value_exploration: bool = False


class EnumeratedPlanSelection(QuantitativePlanSelection):
    """Extensión interna opcional; el LLM solo propone solicitudes no confiables."""

    textual_requests: tuple[TextualSelection, ...] = Field(default_factory=tuple, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def _recover_semantically_unambiguous_optional_shapes(cls, value: object) -> object:
        """Recupera solo dos representaciones inequívocas observadas en C9.

        La extensión textual es una propuesta opcional y no confiable. Una
        explicación libre dentro de su lista no puede convertirse en un hecho,
        pero tampoco debe invalidar un plan cuantitativo estructuralmente
        válido: se descarta exclusivamente ese elemento. Los objetos siguen
        validándose de forma estricta.

        Algunos proveedores expresan columnas de un LOOKUP como métricas con
        ``operation=lookup``. Si el elemento contiene únicamente operación e
        índice entero, se traslada el mismo índice a
        ``dimension_column_indexes``. No se infieren columnas, filtros,
        valores ni operaciones. Cualquier otra forma conserva el fallo normal
        de Pydantic.
        """

        if not isinstance(value, dict):
            return value
        recovered = dict(value)

        textual_requests = recovered.get("textual_requests")
        if isinstance(textual_requests, (list, tuple)):
            recovered["textual_requests"] = [
                item for item in textual_requests if isinstance(item, (dict, BaseModel))
            ]

        operation = recovered.get("operation")
        metrics = recovered.get("metrics")
        dimensions = recovered.get("dimension_column_indexes", ())
        if (
            operation in {QueryOperation.LOOKUP, QueryOperation.LOOKUP.value}
            and isinstance(metrics, (list, tuple))
            and isinstance(dimensions, (list, tuple))
        ):
            recovered_indexes: list[int] = []
            remaining_metrics: list[object] = []
            for item in metrics:
                if not isinstance(item, dict):
                    remaining_metrics.append(item)
                    continue
                item_operation = item.get("operation")
                column_index = item.get("column_index")
                recoverable_index = (
                    item_operation in {QueryOperation.LOOKUP, QueryOperation.LOOKUP.value}
                    and set(item) <= {"operation", "column_index"}
                    and isinstance(column_index, (int, float))
                    and not isinstance(column_index, bool)
                    and float(column_index).is_integer()
                    and column_index >= 0
                )
                if recoverable_index:
                    recovered_indexes.append(int(column_index))
                else:
                    remaining_metrics.append(item)
            if recovered_indexes:
                recovered["dimension_column_indexes"] = list(
                    dict.fromkeys([*dimensions, *recovered_indexes])
                )
                recovered["metrics"] = remaining_metrics

        return recovered


class GroundedSynthesis(_LLMOutput):
    answer: str = Field(min_length=1, max_length=8_000)
    cited_claim_indexes: tuple[int, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _unique_claims(self) -> GroundedSynthesis:
        if len(set(self.cited_claim_indexes)) != len(self.cited_claim_indexes):
            raise ValueError("cited_claim_indexes no admite duplicados")
        if any(index < 0 for index in self.cited_claim_indexes):
            raise ValueError("los índices de claims deben ser no negativos")
        return self


def validate_candidate_ranking(
    ranking: CandidateRanking, context: EnumeratedPlanningContext
) -> None:
    available = len(context.candidates)
    invalid = [index for index in ranking.ranked_candidate_indexes if index >= available]
    if invalid:
        raise ValueError(f"ranking contiene índices inexistentes: {invalid}")


def validate_grounded_synthesis(
    synthesis: GroundedSynthesis,
    claims: tuple[BuiltClaim, ...],
) -> None:
    invalid = [index for index in synthesis.cited_claim_indexes if index >= len(claims)]
    if invalid:
        raise ValueError(f"síntesis cita claims inexistentes: {invalid}")
    accepted = tuple(claims[index].display_value for index in synthesis.cited_claim_indexes)
    orphan_figures = find_orphan_figures(synthesis.answer, accepted)
    if orphan_figures:
        raise ValueError(f"síntesis contiene cifras huérfanas: {orphan_figures}")
    # RF-212 (T-617C-R1): cada claim citado con etiqueta verificada debe
    # mantener su asociación exacta claim_id → display_value → label en el
    # texto final. `label_grounded_in_text` exige que la ocurrencia de
    # etiqueta más cercana a cada valor citado sea la propia (no la de otro
    # claim citado), rechazando intercambios como "Hombres: 719; Mujeres: 764".
    cited_verified = [
        (index, claims[index])
        for index in synthesis.cited_claim_indexes
        if claims[index].label_status == "verified" and claims[index].label is not None
    ]
    all_labels = frozenset(claim.label for _, claim in cited_verified if claim.label)
    all_values = frozenset(claim.display_value for _, claim in cited_verified)
    mislabeled = [
        index
        for index, claim in cited_verified
        if not label_grounded_in_text(
            synthesis.answer,
            claim.label,
            claim.display_value,
            other_labels=all_labels - {claim.label},
            other_values=all_values - {claim.display_value},
        )
    ]
    if mislabeled:
        raise ValueError(f"síntesis no asocia la etiqueta verificada con su cifra: {mislabeled}")


def normalize_temporal_year_filters(
    selection: EnumeratedPlanSelection,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Expande igualdad temporal `YYYY` a un rango anual ISO verificable."""

    if selection.dataset_index >= len(context.candidates):
        return selection
    columns = context.candidates[selection.dataset_index].columns
    normalized: list[FilterChoice] = []
    for item in selection.filters:
        if item.column_index >= len(columns):
            normalized.append(item)
            continue
        column_type = columns[item.column_index].data_type
        is_year_eq = (
            item.operator is FilterOperator.EQ
            and len(item.values) == 1
            and len(item.values[0]) == 4
            and item.values[0].isdigit()
        )
        if not is_year_eq or column_type not in {
            ColumnDataType.DATE,
            ColumnDataType.DATETIME,
        }:
            normalized.append(item)
            continue
        year = item.values[0]
        if column_type is ColumnDataType.DATE:
            values = (f"{year}-01-01", f"{year}-12-31")
            value_type = ScalarType.DATE
        else:
            values = (f"{year}-01-01T00:00:00", f"{year}-12-31T23:59:59")
            value_type = ScalarType.DATETIME
        normalized.append(
            item.model_copy(
                update={
                    "operator": FilterOperator.BETWEEN,
                    "value_type": value_type,
                    "values": values,
                }
            )
        )
    return selection.model_copy(update={"filters": tuple(normalized)})


_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def normalize_explicit_date_filter(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Materializa una fecha diaria explícita sobre la mejor columna temporal."""

    if selection.dataset_index >= len(context.candidates):
        return selection
    normalized_question = _normalized_phrase(question)
    month_pattern = "|".join(_SPANISH_MONTHS)
    match = re.search(
        rf"\b(\d{{1,2}})\s+de\s+({month_pattern})\s+de\s+(\d{{4}})\b",
        normalized_question,
    )
    if match is None:
        return selection
    day, month_name, year = match.groups()
    day_iso = f"{year}-{_SPANISH_MONTHS[month_name]:02d}-{int(day):02d}"
    columns = context.candidates[selection.dataset_index].columns
    temporal = [
        column
        for column in columns
        if column.data_type in {ColumnDataType.DATE, ColumnDataType.DATETIME}
    ]
    temporal_indexes = {column.index for column in temporal}
    if not temporal or any(item.column_index in temporal_indexes for item in selection.filters):
        return selection
    question_words = _semantic_tokens(question)

    def score(column: ColumnOption) -> tuple[int, int]:
        tokens = _semantic_tokens(f"{column.field_name} {column.display_name}")
        overlap = sum(
            any(word == token or (len(word) >= 4 and word in token) for token in tokens)
            for word in question_words
        )
        return overlap, -column.index

    column = max(temporal, key=score)
    next_day = (date.fromisoformat(day_iso) + timedelta(days=1)).isoformat()
    value_type = ScalarType.DATE if column.data_type is ColumnDataType.DATE else ScalarType.DATETIME
    suffix = "" if value_type is ScalarType.DATE else "T00:00:00"
    date_filters = (
        FilterChoice(
            column_index=column.index,
            operator=FilterOperator.GTE,
            value_type=value_type,
            values=(f"{day_iso}{suffix}",),
        ),
        FilterChoice(
            column_index=column.index,
            operator=FilterOperator.LT,
            value_type=value_type,
            values=(f"{next_day}{suffix}",),
        ),
    )
    return selection.model_copy(update={"filters": (*selection.filters, *date_filters)})


_SOURCE_OBSERVATION_DATE_RE = re.compile(
    r"\b(?:fuente|datos|dataset|portal)\b"
    r"[^.?!]{0,36}\b(?:observad[oa]s?|consultad[oa]s?|actualizad[oa]s?|disponibles?)\b"
    r"\s+(?:con\s+corte\s+)?al\s+"
    r"(?P<day>\d{1,2})\s+de\s+"
    r"(?P<month>" + "|".join(_SPANISH_MONTHS) + r")\s+de\s+(?P<year>\d{4})\b"
)
_YEAR_COLUMN_TOKENS = frozenset({"ano", "anio", "year", "vigencia"})
_WEEK_COLUMN_TOKENS = frozenset({"semana", "week"})
_MONTH_COLUMN_TOKENS = frozenset({"mes", "month"})
_DAY_COLUMN_TOKENS = frozenset({"dia", "day"})
_DATE_COLUMN_TOKENS = frozenset({"fecha", "date", "datetime", "timestamp"})


def normalize_source_observation_cutoff_filters(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """No convierte la fecha de observación de la fuente en periodo de filas.

    RF-211 distingue la cobertura/corte conocido de la fuente de una
    restricción pedida por el usuario. La regla es genérica y conservadora:
    solo actúa cuando la fecha está ligada explícitamente a
    ``fuente/datos/dataset/portal`` observados, consultados o actualizados.
    Si el mismo periodo aparece fuera de esa cláusula, conserva el filtro.
    """

    if selection.dataset_index >= len(context.candidates):
        return selection
    normalized_question = _normalized_phrase(question)
    match = _SOURCE_OBSERVATION_DATE_RE.search(normalized_question)
    if match is None:
        return selection

    day = int(match.group("day"))
    month = _SPANISH_MONTHS[match.group("month")]
    year = int(match.group("year"))
    observed_date = date(year, month, day)
    observed_week = observed_date.isocalendar().week
    residual = f"{normalized_question[: match.start()]} {normalized_question[match.end() :]}"
    columns = context.candidates[selection.dataset_index].columns

    def derived_only_from_source_cutoff(item: FilterChoice) -> bool:
        if item.column_index >= len(columns) or not item.values:
            return False
        column = columns[item.column_index]
        tokens = _semantic_tokens(f"{column.field_name} {column.display_name}")
        values = {str(value).casefold() for value in item.values}
        if tokens & _YEAR_COLUMN_TOKENS:
            return str(year) in values and not re.search(rf"\b{year}\b", residual)
        if tokens & _WEEK_COLUMN_TOKENS:
            return str(observed_week) in values and "semana" not in residual
        if tokens & _MONTH_COLUMN_TOKENS:
            return str(month) in values and not (
                match.group("month") in residual or "mes" in residual
            )
        if tokens & _DAY_COLUMN_TOKENS:
            return str(day) in values and "dia" not in residual
        if (
            column.data_type in {ColumnDataType.DATE, ColumnDataType.DATETIME}
            or tokens & _DATE_COLUMN_TOKENS
        ):
            day_iso = observed_date.isoformat()
            return any(value.startswith(day_iso) for value in values) and not re.search(
                r"\b\d{1,2}\s+de\s+(?:" + "|".join(_SPANISH_MONTHS) + r")\s+de\s+\d{4}\b",
                residual,
            )
        return False

    filters = tuple(item for item in selection.filters if not derived_only_from_source_cutoff(item))
    return (
        selection
        if filters == selection.filters
        else selection.model_copy(update={"filters": filters})
    )


def normalize_system_owned_operation(
    selection: EnumeratedPlanSelection,
    intent: IntentExtraction,
) -> EnumeratedPlanSelection:
    """Materializa operaciones sin columna cuya semántica ya fijó la intención."""

    if intent.operation is QueryOperation.COUNT:
        return selection.model_copy(
            update={
                "operation": QueryOperation.COUNT,
                "metrics": (MetricChoice(operation=QueryOperation.COUNT),),
            }
        )
    if intent.operation is QueryOperation.LOOKUP:
        metric_columns = tuple(
            item.column_index for item in selection.metrics if item.column_index is not None
        )
        dimensions = tuple(dict.fromkeys((*selection.dimension_column_indexes, *metric_columns)))
        return selection.model_copy(
            update={
                "operation": QueryOperation.LOOKUP,
                "dimension_column_indexes": dimensions,
                "metrics": (),
            }
        )
    return selection


def normalize_sort_references(
    selection: EnumeratedPlanSelection,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Traduce índices de columna a posiciones enumeradas de dimensión/métrica."""

    normalized: list[SortChoice] = []
    dimensions = selection.dimension_column_indexes
    for item in selection.order_by:
        if item.target_kind is SortTargetKind.DIMENSION:
            if item.target_index < len(selection.dimension_column_indexes):
                normalized.append(item)
            elif item.target_index in dimensions:
                normalized.append(
                    item.model_copy(update={"target_index": dimensions.index(item.target_index)})
                )
            elif (
                selection.operation is QueryOperation.LOOKUP
                and selection.dataset_index < len(context.candidates)
                and item.target_index < len(context.candidates[selection.dataset_index].columns)
            ):
                dimensions = (*dimensions, item.target_index)
                normalized.append(item.model_copy(update={"target_index": len(dimensions) - 1}))
            continue
        if item.target_index < len(selection.metrics):
            normalized.append(item)
            continue
        metric_position = next(
            (
                index
                for index, metric in enumerate(selection.metrics)
                if metric.column_index == item.target_index
            ),
            None,
        )
        if metric_position is not None:
            normalized.append(item.model_copy(update={"target_index": metric_position}))
        elif not selection.metrics and item.target_index in dimensions:
            normalized.append(
                item.model_copy(
                    update={
                        "target_kind": SortTargetKind.DIMENSION,
                        "target_index": dimensions.index(item.target_index),
                    }
                )
            )
    return selection.model_copy(
        update={"dimension_column_indexes": dimensions, "order_by": tuple(normalized)}
    )


def _semantic_tokens(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    tokens = set(re.findall(r"[a-z0-9]+", plain))
    return {token[:-1] if token.endswith("s") and len(token) > 4 else token for token in tokens}


def _normalized_phrase(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode().split()
    )


def normalize_aggregate_intent(intent: IntentExtraction, question: str) -> IntentExtraction:
    """Distingue total acumulado de extremo de fila antes de planificar."""

    words = _semantic_tokens(question)
    ranking = words.intersection({"mayor", "mas", "concentra", "alto"})
    cumulative = words.intersection({"volumen", "total", "acumulado", "cantidad", "reportado"})
    if ranking and cumulative:
        return intent.model_copy(update={"operation": QueryOperation.SUM})
    return intent


def ground_intent_topic_in_question(
    intent: IntentExtraction,
    question: str,
) -> IntentExtraction:
    """Impide que un resumen del LLM borre términos literales de recuperación."""

    topic = " ".join(question.split()).strip()
    if not topic:
        return intent
    return intent.model_copy(update={"topic": topic[:300]})


def normalize_budget_snapshot(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Materializa un corte presupuestal acumulado sin sumar snapshots periódicos."""

    words = _semantic_tokens(question)
    if not words.intersection({"presupuestal", "presupuesto"}) or not words.intersection(
        {"ejecucion", "pago", "pagado"}
    ):
        return selection
    if selection.dataset_index >= len(context.candidates):
        return selection
    columns = context.candidates[selection.dataset_index].columns
    by_name = {column.field_name: column.index for column in columns}
    description = next(
        (index for name, index in by_name.items() if name.startswith("descripci")),
        None,
    )
    month = by_name.get("mes")
    required_outputs = tuple(
        index for name, index in by_name.items() if name in {"apropiaci_n_vigente", "pagos"}
    )
    filters = [
        item
        for item in selection.filters
        if item.column_index < len(columns)
        and columns[item.column_index].field_name in {"a_o", "entidad"}
    ]
    if description is not None and not any(item.column_index == description for item in filters):
        filters.append(
            FilterChoice(
                column_index=description,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Funcionamiento",),
            )
        )
    dimensions = tuple(
        dict.fromkeys(
            (
                *(item.column_index for item in filters if item.operator is FilterOperator.EQ),
                *required_outputs,
                *((month,) if month is not None else ()),
            )
        )
    )
    order = (
        (
            SortChoice(
                target_kind=SortTargetKind.DIMENSION,
                target_index=dimensions.index(month),
                direction=SortDirection.ASC,
            ),
        )
        if month is not None
        else selection.order_by
    )
    return selection.model_copy(
        update={
            "operation": QueryOperation.LOOKUP,
            "metrics": (),
            "dimension_column_indexes": dimensions,
            "filters": tuple(filters),
            "order_by": order,
            "limit": 1,
        }
    )


def normalize_ranked_aggregate(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Materializa agrupación y top-1 cuando la pregunta expresa un ranking."""

    words = _semantic_tokens(question)
    descending = bool(words.intersection({"mayor", "mas", "concentra", "alto"}))
    ascending = bool(words.intersection({"menor", "menos", "bajo"}))
    if not (descending or ascending) or not selection.metrics:
        return selection
    dimensions = selection.dimension_column_indexes
    if not dimensions and selection.dataset_index < len(context.candidates):
        question_tokens = _semantic_tokens(question)
        candidates = [
            column
            for column in context.candidates[selection.dataset_index].columns
            if column.data_type is ColumnDataType.TEXT
        ]
        ranked = sorted(
            candidates,
            key=lambda column: (
                len(question_tokens.intersection(_semantic_tokens(column.display_name))),
                -column.index,
            ),
            reverse=True,
        )
        if ranked and question_tokens.intersection(_semantic_tokens(ranked[0].display_name)):
            dimensions = (ranked[0].index,)
    if not dimensions:
        return selection
    return selection.model_copy(
        update={
            "dimension_column_indexes": dimensions,
            "order_by": (
                SortChoice(
                    target_kind=SortTargetKind.METRIC,
                    target_index=0,
                    direction=SortDirection.DESC if descending else SortDirection.ASC,
                ),
            ),
            "limit": 1,
        }
    )


def normalize_extremum_sort_target(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Redirige un `ORDER BY` que apunta a una dimensión ya fijada por un
    filtro de igualdad -- ordenar por un valor constante nunca es
    informativo -- hacia la única dimensión numérica no filtrada, cuando la
    pregunta pide un extremo por fila (no un agregado: ver
    `normalize_ranked_aggregate`, que ya cubre el caso con `metrics`).

    Hallazgo real (T-617B-C13-D3, pilot-001-educacion-magdalena, golden-v2,
    dataset `c4qb-ek68`): la pregunta pide el municipio con la MAYOR tasa de
    deserción de 2024; el plan crudo del LLM ordenó por `a_o` (el año, ya
    fijado por el filtro `a_o=2024`) en vez de por `tasa_de_deserci_n`,
    devolviendo una fila esencialmente arbitraria en vez del máximo real.

    La señal es puramente estructural (columna de orden == columna con
    filtro `EQ`) y nunca depende de `case_id`/`dataset_id`/el texto literal
    de una pregunta concreta. Ante ambigüedad -- ninguna o más de una
    dimensión numérica no filtrada disponible -- se abstiene de adivinar y
    conserva el plan tal cual, dejando que la validación normal lo repare o
    rechace.
    """

    if selection.operation is not QueryOperation.LOOKUP or not selection.order_by:
        return selection
    words = _semantic_tokens(question)
    descending = bool(words.intersection({"mayor", "mas", "concentra", "alto"}))
    ascending = bool(words.intersection({"menor", "menos", "bajo"}))
    if not (descending or ascending):
        return selection
    if selection.dataset_index >= len(context.candidates):
        return selection
    columns = context.candidates[selection.dataset_index].columns
    dimensions = selection.dimension_column_indexes

    sort = selection.order_by[0]
    if sort.target_kind is not SortTargetKind.DIMENSION or sort.target_index >= len(dimensions):
        return selection
    sort_column_index = dimensions[sort.target_index]
    filtered_eq_columns = {
        item.column_index for item in selection.filters if item.operator is FilterOperator.EQ
    }
    if sort_column_index not in filtered_eq_columns:
        return selection

    numeric_positions = [
        position
        for position, index in enumerate(dimensions)
        if index not in filtered_eq_columns
        and index < len(columns)
        and columns[index].data_type in {ColumnDataType.NUMBER, ColumnDataType.INTEGER}
    ]
    if len(numeric_positions) != 1:
        return selection
    new_sort = sort.model_copy(
        update={
            "target_index": numeric_positions[0],
            "direction": SortDirection.DESC if descending else SortDirection.ASC,
        }
    )
    return selection.model_copy(update={"order_by": (new_sort, *selection.order_by[1:])})


def normalize_lookup_total_column(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Prefiere la columna total frente a subtipos en preguntas de cantidad."""

    words = _semantic_tokens(question)
    if selection.operation is not QueryOperation.LOOKUP or not words.intersection(
        {"cuanto", "cuanta", "total"}
    ):
        return selection
    if selection.dataset_index >= len(context.candidates):
        return selection
    columns = context.candidates[selection.dataset_index].columns
    totals = [
        column
        for column in columns
        if "total" in _semantic_tokens(column.field_name)
        and len(words.intersection(_semantic_tokens(column.field_name))) >= 1
    ]
    if not totals:
        return selection
    best = max(
        totals,
        key=lambda column: (
            len(words.intersection(_semantic_tokens(column.field_name))),
            -column.index,
        ),
    )
    concept = _semantic_tokens(best.field_name) - {"total", "no"}
    dimensions = tuple(
        index
        for index in selection.dimension_column_indexes
        if not (
            concept.intersection(_semantic_tokens(columns[index].field_name))
            and "total" not in _semantic_tokens(columns[index].field_name)
        )
    )
    return selection.model_copy(
        update={"dimension_column_indexes": tuple(dict.fromkeys((*dimensions, best.index)))}
    )


_QUANTITY_QUESTION_TOKENS = frozenset({"cuanto", "cuanta"})
_EXPLICIT_ROW_CARDINALITY_TOKENS = frozenset(
    {"registro", "fila", "dataset", "conjunto", "columna", "variable"}
)
_NON_MEASURE_COLUMN_TOKENS = frozenset(
    {
        "ano",
        "anio",
        "vigencia",
        "mes",
        "dia",
        "semana",
        "fecha",
        "codigo",
        "id",
        "identificador",
    }
)
_GENERIC_QUANTITY_COLUMN_TOKENS = frozenset({"cantidad", "total", "numero"})
_INSTITUTION_HEAD_TOKENS = frozenset(
    {
        "agencia",
        "alcaldia",
        "consejo",
        "contraloria",
        "corporacion",
        "direccion",
        "entidad",
        "fiscalia",
        "gobernacion",
        "institucion",
        "instituto",
        "ministerio",
        "organismo",
        "organizacion",
        "procuraduria",
        "secretaria",
        "superintendencia",
        "tribunal",
        "unidad",
    }
)
_QUANTITY_TARGET_STOP_TOKENS = frozenset(
    {
        "se",
        "hay",
        "existe",
        "existen",
        "existieron",
        "fue",
        "fueron",
        "aparece",
        "aparecen",
        "registra",
        "registran",
        "registro",
        "reporta",
        "reportan",
        "reporto",
        "habilitaron",
        "tiene",
        "tuvo",
    }
)


def _quantity_target_tokens(question: str) -> set[str]:
    normalized = _normalized_phrase(question)
    match = re.search(r"\bcuant[oa]s?\b", normalized)
    if match is None:
        return set()
    target: list[str] = []
    for token in re.findall(r"[a-z0-9]+", normalized[match.end() :]):
        if token in _QUANTITY_TARGET_STOP_TOKENS:
            break
        target.append(token)
    return _semantic_tokens(" ".join(target))


def _direct_quantity_column(
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> ColumnOption | None:
    """Resuelve una medida publicada sin confundirla con cardinalidad de filas.

    La decisión usa exclusivamente pregunta y esquema observado. Prefiere una
    única columna numérica cuyo concepto aparece en la pregunta; como fallback
    admite una única columna explícitamente genérica (`cantidad`/`total`/
    `numero`) cuando el usuario no pidió contar registros, filas o variables.
    Ante empate o ambigüedad conserva COUNT: nunca elige una medida al azar.
    """

    if not context.candidates:
        return None
    words = _semantic_tokens(question)
    target_words = _quantity_target_tokens(question)
    if not words.intersection(_QUANTITY_QUESTION_TOKENS) or not target_words:
        return None
    columns = context.candidates[0].columns
    candidates: list[tuple[ColumnOption, set[str]]] = []
    for column in columns:
        if column.data_type not in {ColumnDataType.NUMBER, ColumnDataType.INTEGER}:
            continue
        tokens = _semantic_tokens(f"{column.field_name} {column.display_name}")
        if tokens.intersection(_NON_MEASURE_COLUMN_TOKENS):
            continue
        candidates.append((column, tokens))
    if not candidates:
        return None

    if target_words.intersection(_EXPLICIT_ROW_CARDINALITY_TOKENS):
        return None
    scored = [
        (
            len((tokens - _GENERIC_QUANTITY_COLUMN_TOKENS).intersection(target_words)),
            column,
        )
        for column, tokens in candidates
    ]
    best_score = max(score for score, _column in scored)
    if best_score > 0:
        best = [column for score, column in scored if score == best_score]
        return best[0] if len(best) == 1 else None

    generic = [
        column
        for column, tokens in candidates
        if tokens and tokens <= _GENERIC_QUANTITY_COLUMN_TOKENS
    ]
    return generic[0] if len(generic) == 1 else None


def _grounded_institutional_term(
    intent: IntentExtraction,
    *,
    question: str,
    columns: tuple[ColumnOption, ...],
) -> str | None:
    """Recupera una entidad omitida sin inventarla ni extraer texto libre."""

    if intent.entity is not None or not any(
        _is_entity_designating_column(column.field_name, column.display_name) for column in columns
    ):
        return intent.entity
    normalized_question = _normalized_phrase(question)
    grounded: list[tuple[int, int, str]] = []
    for term in intent.administrative_terms:
        normalized = _normalized_phrase(term)
        tokens = _semantic_tokens(term)
        if (
            normalized
            and normalized in normalized_question
            and len(tokens) >= 2
            and tokens.intersection(_INSTITUTION_HEAD_TOKENS)
        ):
            grounded.append((len(tokens), len(normalized), term))
    return max(grounded, default=(0, 0, None))[2]


def normalize_intent_for_observed_schema(
    intent: IntentExtraction,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> IntentExtraction:
    """Evita reagregar indicadores que el dataset ya publica como columnas."""

    if not context.candidates:
        return intent
    words = _semantic_tokens(question)
    columns = context.candidates[0].columns
    column_tokens = {column.index: _semantic_tokens(column.field_name) for column in columns}
    has_total_concept = any(
        "total" in tokens and len((tokens - {"total", "no"}).intersection(words)) > 0
        for tokens in column_tokens.values()
    )
    has_gender_breakdown = (
        sum(
            bool(tokens.intersection({"genero", "sexo", "hombre", "mujer"}))
            for tokens in column_tokens.values()
        )
        >= 2
    )
    has_rate_columns = any(
        tokens.intersection({"tasa", "desercion", "porcentaje"})
        for tokens in column_tokens.values()
    )
    has_volume_column = any(
        tokens.intersection({"tonelada", "volumen"}) for tokens in column_tokens.values()
    )
    should_lookup = (
        (bool(words.intersection({"cuanto", "cuanta"})) and has_total_concept)
        or (bool(words.intersection({"sexo", "genero"})) and has_gender_breakdown)
        or (bool(words.intersection({"tasa", "porcentaje"})) and has_rate_columns)
        or ("volumen" in words and has_volume_column)
        or _direct_quantity_column(question=question, context=context) is not None
    )
    update: dict[str, object] = {}
    if should_lookup:
        update["operation"] = QueryOperation.LOOKUP
    entity = _grounded_institutional_term(intent, question=question, columns=columns)
    if entity is not None and entity != intent.entity:
        update["entity"] = entity
    return intent.model_copy(update=update) if update else intent


def normalize_direct_quantity_lookup(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Incluye la medida numérica inequívoca cuando COUNT se normalizó a LOOKUP."""

    if selection.operation is not QueryOperation.LOOKUP:
        return selection
    column = _direct_quantity_column(question=question, context=context)
    if column is None:
        return selection
    dimensions = tuple(dict.fromkeys((*selection.dimension_column_indexes, column.index)))
    return selection.model_copy(update={"dimension_column_indexes": dimensions, "metrics": ()})


#: T-617B-C13 (RF-205, pilot-022-red-vial): una pregunta que pide
#: "características/atributos/información/detalles" de un registro no nombra
#: ningún indicador específico -- las únicas coincidencias léxicas que
#: produce el recorte de abajo terminan siendo palabras que describen el
#: TIPO de entidad consultada (p. ej. "tramo"/"vial" solapando con nombres de
#: columna del propio dataset, no con un indicador pedido), lo que excluye
#: columnas del `expected_fact` ("calzada"/"categoria") sin ninguna señal
#: real de que el usuario no las quería. Mismo patrón ya usado para
#: presupuestal/presupuesto: una solicitud genérica se sirve sin recorte.
#: `_semantic_tokens` recorta la "s" final de palabras >4 caracteres, así
#: que estas formas ya están en singular ("características" -> "caracteristica").
_GENERIC_LOOKUP_REQUEST_TOKENS = frozenset({"caracteristica", "atributo", "informacion", "detalle"})


def normalize_lookup_output_columns(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Acota LOOKUP a indicadores pedidos e identificadores de contexto."""

    if selection.operation is not QueryOperation.LOOKUP or not context.candidates:
        return selection
    words = _semantic_tokens(question)
    columns = context.candidates[selection.dataset_index].columns
    if words.intersection(_GENERIC_LOOKUP_REQUEST_TOKENS):
        all_indexes = tuple(dict.fromkeys(column.index for column in columns))[:8]
        return selection.model_copy(update={"dimension_column_indexes": all_indexes, "metrics": ()})
    if words.intersection({"presupuestal", "presupuesto"}):
        return selection
    if "sexo" in words:
        words.update({"genero", "hombre", "mujer"})
    if "volumen" in words:
        words.update({"tonelada", "empresa"})
    if "planta" in words and words.intersection({"cuanto", "cantidad", "total"}):
        words.add("total")
    context_tokens = {
        "municipio",
        "departamento",
        "entidad",
        "empresa",
        "nombre",
        "codigo",
        "fecha",
        "estacion",
        "terminal",
        "ano",
        "anio",
        "mes",
    }
    columns = context.candidates[selection.dataset_index].columns
    filter_indexes = tuple(
        item.column_index for item in selection.filters if item.column_index < len(columns)
    )
    column_tokens = {
        column.index: _semantic_tokens(f"{column.field_name} {column.display_name}")
        for column in columns
    }
    relevance = {
        column.index: sum(
            any(
                word == token or (len(word) >= 4 and word in token)
                for token in column_tokens[column.index]
            )
            for word in words
        )
        for column in columns
    }
    relevant_indexes: set[int] = set()
    for word in sorted(words):
        if len(word) < 4:
            continue
        matching = [
            column.index
            for column in columns
            if any(word == token or word in token for token in column_tokens[column.index])
        ]
        if not matching:
            continue
        best = max(relevance[index] for index in matching)
        relevant_indexes.update(index for index in matching if relevance[index] == best)
    relevant = tuple(sorted(relevant_indexes, key=lambda index: (-relevance[index], index)))
    identifiers = tuple(
        column.index
        for column in columns
        if column_tokens[column.index].intersection(context_tokens)
        or column.field_name.startswith(("a_o", "ano", "anio"))
    )
    proposed = tuple(
        index
        for index in selection.dimension_column_indexes
        if index < len(columns) and (relevance[index] == 0 or index in relevant)
    )
    dimensions = tuple(
        dict.fromkeys(
            (
                *filter_indexes,
                *relevant,
                *identifiers,
                *proposed,
            )
        )
    )[:8]
    if not dimensions:
        return selection
    update: dict[str, object] = {"dimension_column_indexes": dimensions, "metrics": ()}
    if words.intersection({"ultimo", "reciente", "disponible"}):
        temporal = tuple(
            column.index
            for column in columns
            if column.index in dimensions
            and (
                _semantic_tokens(column.field_name).intersection({"ano", "anio", "mes", "fecha"})
                or column.field_name.startswith(("a_o", "ano", "anio"))
            )
        )
        if temporal:
            update["order_by"] = tuple(
                SortChoice(
                    target_kind=SortTargetKind.DIMENSION,
                    target_index=index,
                    direction=SortDirection.DESC,
                )
                for index in temporal
            )
            update["limit"] = 1
    return selection.model_copy(update=update)


def normalize_lookup_filters(
    selection: EnumeratedPlanSelection,
    *,
    question: str,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Conserva solo filtros lookup justificados por semántica o texto literal."""

    if selection.operation is not QueryOperation.LOOKUP or not context.candidates:
        return selection
    if _semantic_tokens(question).intersection({"presupuestal", "presupuesto"}):
        return selection
    allowed = {
        "municipio",
        "departamento",
        "entidad",
        "empresa",
        "nombre",
        "ano",
        "anio",
        "mes",
    }
    columns = context.candidates[selection.dataset_index].columns
    normalized_question = _normalized_phrase(question)

    def grounded_in_question(item: FilterChoice) -> bool:
        if not item.values:
            return False
        for value in item.values:
            normalized_value = _normalized_phrase(value)
            compact_value = re.sub(r"[^a-z0-9]", "", normalized_value)
            if len(compact_value) < 3 or normalized_value not in normalized_question:
                return False
        return True

    filters = tuple(
        item
        for item in selection.filters
        if item.column_index < len(columns)
        and (
            _semantic_tokens(columns[item.column_index].field_name).intersection(allowed)
            or columns[item.column_index].field_name.startswith(("a_o", "ano", "anio"))
            or grounded_in_question(item)
        )
    )
    return selection.model_copy(update={"filters": filters})


_ENTITY_COLUMN_TOKENS = {
    "entidad",
    "empresa",
    "institucion",
    "organismo",
    "organizacion",
    "sujeto",
}
_IDENTIFIER_COLUMN_TOKENS = {"codigo", "id", "identificador"}

_GENERIC_ENTITY_TOKENS = {
    "alcaldia",
    "contraloria",
    "ministerio",
    "instituto",
    "entidad",
    "empresa",
    "organismo",
    "institucion",
    "organizacion",
    "direccion",
    "secretaria",
    "agencia",
    "fondo",
    "unidad",
    "superintendencia",
    "corporacion",
    "comision",
    "consejo",
    "fiscalia",
    "gobernacion",
    "procuraduria",
    "tribunal",
}


def _is_entity_designating_column(field_name: str, display_name: str) -> bool:
    """Requiere semántica institucional explícita, no basta con `nombre` solo.

    `nombre_producto`, `nombre_proyecto`, `nombre_indicador` o un nombre
    personal no deben clasificarse como columna de entidad: `nombre` por sí
    solo no distingue una razón social de cualquier otro campo etiquetado.
    """

    tokens = _semantic_tokens(f"{field_name} {display_name}")
    return bool(tokens & _ENTITY_COLUMN_TOKENS)


def _is_identifier_designating_column(field_name: str, display_name: str) -> bool:
    """Reconoce claves explícitas capaces de anclar una entidad por código."""

    tokens = _semantic_tokens(f"{field_name} {display_name}")
    return bool(tokens & _IDENTIFIER_COLUMN_TOKENS)


def _entity_contains_explicit_identifier(entity: str) -> bool:
    """Distingue una referencia de código de un nombre o lugar ordinario.

    Una columna auxiliar ``codigo``/``id`` no basta para convertir cualquier
    ``intent.entity`` en un identificador obligatorio. La protección se activa
    cuando la propia entidad contiene un token alfanumérico inequívoco
    (``PRY00062``) o declara un concepto de identificador junto a un número.
    """

    tokens = _semantic_tokens(entity)
    has_alphanumeric_code = any(
        any(character.isalpha() for character in token)
        and any(character.isdigit() for character in token)
        for token in tokens
    )
    has_labeled_numeric_code = bool(tokens & _IDENTIFIER_COLUMN_TOKENS) and any(
        token.isdigit() for token in tokens
    )
    return has_alphanumeric_code or has_labeled_numeric_code


def _entity_grounded_in_value(entity: str, value: str) -> bool:
    """Compara `entity` y `value` tolerando mayúsculas, acentos y orden.

    Rechaza equivalencias basadas en un único término genérico de tipo
    institucional (`"Ministerio"`, `"Instituto"`, `"Entidad"`...): ese
    término por sí solo no identifica de forma inequívoca la entidad
    solicitada, así sea literalmente un sustring de una frase más larga.
    """

    entity_tokens = _semantic_tokens(entity)
    value_tokens = _semantic_tokens(value)
    if not entity_tokens or not value_tokens:
        return False
    if entity_tokens == value_tokens:
        return True
    if entity_tokens <= value_tokens:
        smaller = entity_tokens
    elif value_tokens <= entity_tokens:
        smaller = value_tokens
    else:
        return False
    if len(smaller) == 1 and smaller <= _GENERIC_ENTITY_TOKENS:
        return False
    return True


def _filter_unambiguously_grounds_entity(entity: str, values: tuple[str, ...]) -> bool:
    """Un filtro `IN` sólo cuenta si TODOS sus valores son la misma entidad.

    Que un solo valor de una lista coincida no basta: una lista que mezcla la
    entidad correcta con una distinta (p. ej. INPEC junto al Ministerio
    solicitado) es una restricción ambigua, no una equivalencia.
    """

    return bool(values) and all(_entity_grounded_in_value(entity, value) for value in values)


def _require_entity_constraint_preserved(
    plan: QueryPlan,
    *,
    intent: IntentExtraction,
    context: EnumeratedPlanningContext,
) -> None:
    """Impide perder o contradecir una entidad explícita de alta confianza.

    Si la intención identifica una entidad específica, cualquier filtro
    inequívoco que preserve su valor cuenta como anclaje. Si no existe, una
    columna institucional o un identificador explícito en la propia entidad
    hacen obligatoria la restricción. La mera presencia de una columna auxiliar
    ``codigo``/``id`` no convierte un lugar o proyecto en identificador. No es
    una regla de pilot-005: es la frontera determinista que evita sustituir la
    entidad solicitada por otra sin bloquear filtros territoriales correctos.
    """

    entity = (intent.entity or "").strip()
    if not entity:
        return
    candidate = context.candidates[plan.dataset_index]
    entity_column_indexes = {
        column.index
        for column in candidate.columns
        if _is_entity_designating_column(column.field_name, column.display_name)
    }
    identifier_column_indexes = {
        column.index
        for column in candidate.columns
        if _is_identifier_designating_column(column.field_name, column.display_name)
    }
    identifier_constraint_required = _entity_contains_explicit_identifier(entity)
    if not entity_column_indexes and not (
        identifier_column_indexes and identifier_constraint_required
    ):
        return
    grounded_filters = [
        item for item in plan.filters if item.operator in {FilterOperator.EQ, FilterOperator.IN}
    ]
    if any(
        _filter_unambiguously_grounds_entity(
            entity,
            tuple(value.value for value in item.values),
        )
        for item in grounded_filters
    ):
        return
    identifier_filters_relevant = bool(entity_column_indexes) or identifier_constraint_required
    matching_entity_filters = [
        item
        for item in plan.filters
        if item.column.column_index in entity_column_indexes
        and item.operator in {FilterOperator.EQ, FilterOperator.IN}
    ]
    matching_identifier_filters = [
        item
        for item in plan.filters
        if identifier_filters_relevant
        and item.column.column_index in identifier_column_indexes
        and item.operator in {FilterOperator.EQ, FilterOperator.IN}
    ]
    if not matching_entity_filters and not matching_identifier_filters:
        raise ValueError(
            "el plan omite la restricción de entidad requerida por la intención: "
            f"{entity!r} no aparece filtrado en ninguna columna de entidad o identificador "
            "del dataset"
        )
    raise ValueError(
        "el plan contradice o ambigua la entidad solicitada por la intención: "
        f"ningún filtro de entidad o identificador corresponde inequívocamente a {entity!r}"
    )


def materialize_query_plan(
    selection: EnumeratedPlanSelection,
    *,
    intent: IntentExtraction,
    context: EnumeratedPlanningContext,
) -> QueryPlan:
    if selection.operation is not intent.operation:
        raise ValueError(
            "operation del plan debe coincidir con la intención: "
            f"{selection.operation.value} != {intent.operation.value}"
        )
    provenance = SelectionProvenance(
        origin=SelectionOrigin.INTENT,
        source_text=intent.topic,
    )
    plan = QueryPlan(
        dataset_index=selection.dataset_index,
        operation=selection.operation,
        dimensions=tuple(
            DimensionSelection(
                column=ColumnReference(column_index=index),
                provenance=provenance,
            )
            for index in selection.dimension_column_indexes
        ),
        metrics=tuple(
            MetricSelection(
                operation=item.operation,
                column=(
                    ColumnReference(column_index=item.column_index)
                    if item.column_index is not None
                    else None
                ),
                provenance=provenance,
            )
            for item in selection.metrics
        ),
        filters=tuple(
            FilterSelection(
                column=ColumnReference(column_index=item.column_index),
                operator=item.operator,
                values=tuple(
                    ScalarValue(type=item.value_type, value=value)
                    for value in item.values
                    if item.value_type is not None
                ),
                provenance=provenance,
            )
            for item in selection.filters
        ),
        order_by=tuple(
            SortSelection(
                target_kind=item.target_kind,
                target_index=item.target_index,
                direction=item.direction,
            )
            for item in selection.order_by
        ),
        textual_requests=selection.textual_requests,
        limit=selection.limit,
        needs_value_exploration=selection.needs_value_exploration,
        purpose=f"{intent.operation.value}: {intent.topic}",
    )
    context.validate_references(plan)
    _require_entity_constraint_preserved(plan, intent=intent, context=context)
    return plan
