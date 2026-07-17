"""Modelos tipados de hechos fundamentados (T-615B, RF-210).

Este módulo define únicamente el contrato estructural. No construye hechos,
normaliza texto, ejecuta operaciones, calcula hashes, persiste datos ni se
conecta al runtime o a la API pública.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextualFactOperation(StrEnum):
    DIRECT_TEXT = "direct_text"
    VALUE_PRESENCE = "value_presence"
    CATEGORY_SELECTION = "category_selection"
    ARGMAX_LABEL = "argmax_label"
    ARGMIN_LABEL = "argmin_label"
    CANONICAL_TEXT_SET = "canonical_text_set"


class TextNormalizationProfile(StrEnum):
    TEXT_ES_V1 = "text-es-v1"


class TextualFactAlgorithmVersion(StrEnum):
    TEXTUAL_FACT_V1 = "textual-fact-v1"


class TextualFactKind(StrEnum):
    TEXTUAL = "textual"


class QuantitativeFactKind(StrEnum):
    QUANTITATIVE = "quantitative"


class TextualFactTiePolicy(StrEnum):
    REJECT = "reject"


class CategorySelectionRule(StrEnum):
    UNIQUE_NORMALIZED_VALUE = "unique_normalized_value"
    FIRST_BY_VALIDATED_ORDER = "first_by_validated_order"


class EmptyTextualFactOperationParams(_ClosedModel):
    """Parámetros vacíos para `direct_text` y `canonical_text_set`."""


class ValuePresenceParams(_ClosedModel):
    target_raw: str = Field(min_length=1)
    target_normalized: str = Field(min_length=1)


class CategorySelectionParams(_ClosedModel):
    rule: CategorySelectionRule


class ExtremumLabelParams(_ClosedModel):
    label_column: str = Field(min_length=1)
    metric_column: str = Field(min_length=1)
    tie_policy: Literal[TextualFactTiePolicy.REJECT] = TextualFactTiePolicy.REJECT

    @model_validator(mode="after")
    def _columns_are_distinct(self) -> ExtremumLabelParams:
        if self.label_column == self.metric_column:
            raise ValueError("label_column y metric_column deben ser diferentes")
        return self


TextualFactOperationParams = (
    EmptyTextualFactOperationParams
    | ValuePresenceParams
    | CategorySelectionParams
    | ExtremumLabelParams
)


class QuantitativeClaimResponse(_ClosedModel):
    """Forma pública cuantitativa vigente, sin discriminador interno."""

    claim_id: UUID
    claim: str = Field(min_length=1)
    claim_type: Literal["direct", "derived"]
    evidence_id: UUID
    dataset_id: str = Field(pattern=r"^[a-z0-9]{4}-[a-z0-9]{4}$")
    source_row_indexes: tuple[int, ...] = Field(min_length=1)
    columns: tuple[str, ...] = Field(min_length=1)
    formula: dict[str, JsonValue] | None
    raw_value: int | float
    display_value: str = Field(min_length=1)
    unit: str | None
    rounding: int = Field(ge=0)
    source_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class QuantitativeClaim(QuantitativeClaimResponse):
    """Variante cuantitativa del dominio interno.

    `fact_kind` solo existe en esta representación interna. La forma pública
    compatible se obtiene mediante :meth:`to_public_response`.
    """

    fact_kind: Literal[QuantitativeFactKind.QUANTITATIVE] = QuantitativeFactKind.QUANTITATIVE

    def to_public_response(self) -> QuantitativeClaimResponse:
        return QuantitativeClaimResponse.model_validate(self.model_dump(exclude={"fact_kind"}))


class TextualFact(_ClosedModel):
    fact_id: UUID
    fact_kind: Literal[TextualFactKind.TEXTUAL] = TextualFactKind.TEXTUAL
    fact: str = Field(min_length=1)
    operation: TextualFactOperation
    evidence_id: UUID
    dataset_id: str = Field(pattern=r"^[a-z0-9]{4}-[a-z0-9]{4}$")
    source_row_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(
        min_length=1,
        max_length=100,
    )
    columns: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    raw_values: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1,
        max_length=50,
    )
    normalized_values: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1,
        max_length=50,
    )
    display_value: str = Field(min_length=1)
    normalization_profile: Literal[TextNormalizationProfile.TEXT_ES_V1] = (
        TextNormalizationProfile.TEXT_ES_V1
    )
    operation_params: TextualFactOperationParams
    algorithm_version: Literal[TextualFactAlgorithmVersion.TEXTUAL_FACT_V1] = (
        TextualFactAlgorithmVersion.TEXTUAL_FACT_V1
    )
    source_hash: str = Field(pattern=r"^sha256-jcs-v1:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_structural_shape(self) -> TextualFact:
        if tuple(sorted(set(self.source_row_indexes))) != self.source_row_indexes:
            raise ValueError("source_row_indexes debe ser ascendente y no admitir duplicados")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns no admite duplicados")
        if len(self.raw_values) != len(self.normalized_values):
            raise ValueError("raw_values y normalized_values deben tener igual cardinalidad")

        params_type: type[_ClosedModel]
        expected_columns: int
        if self.operation in {
            TextualFactOperation.DIRECT_TEXT,
            TextualFactOperation.CANONICAL_TEXT_SET,
        }:
            params_type = EmptyTextualFactOperationParams
            expected_columns = 1
        elif self.operation is TextualFactOperation.VALUE_PRESENCE:
            params_type = ValuePresenceParams
            expected_columns = 1
        elif self.operation is TextualFactOperation.CATEGORY_SELECTION:
            params_type = CategorySelectionParams
            expected_columns = 1
        else:
            params_type = ExtremumLabelParams
            expected_columns = 2

        if not isinstance(self.operation_params, params_type):
            raise ValueError(
                f"operation_params no corresponde a la operación {self.operation.value}"
            )
        if len(self.columns) != expected_columns:
            raise ValueError(
                f"{self.operation.value} requiere exactamente {expected_columns} columna(s)"
            )
        if self.operation is TextualFactOperation.DIRECT_TEXT:
            if len(self.source_row_indexes) != 1:
                raise ValueError("direct_text requiere exactamente un índice de fila")
            if len(self.raw_values) != 1:
                raise ValueError("direct_text requiere exactamente un valor")
        if isinstance(self.operation_params, ExtremumLabelParams):
            if self.columns != (
                self.operation_params.label_column,
                self.operation_params.metric_column,
            ):
                raise ValueError(
                    "columns debe corresponder a label_column y metric_column, en ese orden"
                )
        return self


GroundedFact = Annotated[
    QuantitativeClaim | TextualFact,
    Field(discriminator="fact_kind"),
]


class GroundedSynthesisPlanSchemaVersion(StrEnum):
    V1 = "grounded-synthesis-plan-v1"


class GroundedSynthesisConnector(StrEnum):
    SIN_CONECTOR = "sin_conector"
    ADEMAS = "ademas"
    POR_OTRA_PARTE = "por_otra_parte"
    EN_CONJUNTO = "en_conjunto"


class GroundedSynthesisTemplate(StrEnum):
    FACT_STATEMENT = "fact_statement"
    SUBJECT_FACT = "subject_fact"
    COMPARISON_PAIR = "comparison_pair"


class GroundedSynthesisClosing(StrEnum):
    SIN_CIERRE = "sin_cierre"
    LIMITACION_DISPONIBILIDAD = "limitacion_disponibilidad"
    ADVERTENCIA_CALIDAD = "advertencia_calidad"


class QuantitativeFactReference(_ClosedModel):
    fact_kind: Literal[QuantitativeFactKind.QUANTITATIVE]
    id: UUID


class TextualFactReference(_ClosedModel):
    fact_kind: Literal[TextualFactKind.TEXTUAL]
    id: UUID


GroundedFactReference = Annotated[
    QuantitativeFactReference | TextualFactReference,
    Field(discriminator="fact_kind"),
]


class GroundedSynthesisSegment(_ClosedModel):
    segment_id: str = Field(min_length=1)
    connector: GroundedSynthesisConnector
    template: GroundedSynthesisTemplate
    fact_refs: tuple[GroundedFactReference, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def _validate_reference_cardinality(self) -> GroundedSynthesisSegment:
        expected = 2 if self.template is GroundedSynthesisTemplate.COMPARISON_PAIR else 1
        if len(self.fact_refs) != expected:
            raise ValueError(f"{self.template.value} requiere exactamente {expected} referencia(s)")
        identities = {(reference.fact_kind, reference.id) for reference in self.fact_refs}
        if len(identities) != len(self.fact_refs):
            raise ValueError("fact_refs no admite referencias duplicadas")
        return self


class GroundedSynthesisPlan(_ClosedModel):
    schema_version: Literal[GroundedSynthesisPlanSchemaVersion.V1] = (
        GroundedSynthesisPlanSchemaVersion.V1
    )
    segments: tuple[GroundedSynthesisSegment, ...] = Field(min_length=1)
    closing: GroundedSynthesisClosing

    @model_validator(mode="after")
    def _validate_unique_segments_and_references(self) -> GroundedSynthesisPlan:
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError("segment_id no admite duplicados")
        references = [
            (reference.fact_kind, reference.id)
            for segment in self.segments
            for reference in segment.fact_refs
        ]
        if len(set(references)) != len(references):
            raise ValueError("una referencia factual no puede repetirse entre segmentos")
        return self
