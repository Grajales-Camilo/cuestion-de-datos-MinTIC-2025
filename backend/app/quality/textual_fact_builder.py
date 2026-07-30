"""Construcción y verificación deterministas de hechos textuales (T-615E).

Satisface RF-401, RF-404 y RF-210. Esta frontera es deliberadamente pura:
recibe un snapshot congelado, no consulta PostgreSQL o Socrata, no llama a un
LLM y no integra el resultado al runtime, API o síntesis.

El SDD no fija texto literal para las seis operaciones. Por eso v1 usa las
frases mínimas y neutrales de ``TEXTUAL_FACT_TEMPLATES``. Solo insertan el
``display_value`` ya calculado por T-615D y son parte de la verificación
exacta del hecho individual; no son el renderer de respuesta de T-615H.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import JsonValue

from app.quality.grounded_facts import (
    TextualFact,
    TextualFactKind,
    TextualFactOperation,
)
from app.quality.textual_facts import (
    TextualEvidence,
    TextualFactSpec,
    TextualOperationError,
    TextualOperationResult,
    evaluate_textual_operation,
)

TextualEligibilityStatus = Literal["eligible", "diagnostic_only", "blocked"]
TextualQualityClassification = Literal["alta", "media", "baja", "no_recomendada"]
FactIdFactory = Callable[[], UUID]

TEXTUAL_FACT_TEMPLATES: Mapping[TextualFactOperation, str] = MappingProxyType(
    {
        TextualFactOperation.DIRECT_TEXT: "El valor observado es {display_value}.",
        TextualFactOperation.VALUE_PRESENCE: "El valor {display_value} está presente.",
        TextualFactOperation.CATEGORY_SELECTION: ("La categoría seleccionada es {display_value}."),
        TextualFactOperation.ARGMAX_LABEL: ("La etiqueta con el valor máximo es {display_value}."),
        TextualFactOperation.ARGMIN_LABEL: ("La etiqueta con el valor mínimo es {display_value}."),
        TextualFactOperation.CANONICAL_TEXT_SET: ("Los valores observados son {display_value}."),
    }
)

_QUANTITATIVE_MARKERS = frozenset(
    {
        "claim_type",
        "count",
        "formula",
        "raw_value",
        "rounding",
        "unit",
    }
)


class TextualFactError(ValueError):
    """Error tipado con código estable, separado de su mensaje explicativo."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TextualEvidenceSnapshot:
    """Vista defensiva del material persistido y de su decisión de calidad.

    Se copia profundamente cada fila y se protege su mapping superior. Esto
    aísla la construcción de mutaciones posteriores del objeto de entrada.
    La arquitectura vigente no persiste el certificado de orden total; cuando
    aplica, el llamador debe aportar esa decisión ya validada como parte del
    snapshot, sin reconsultar ni reescribir la evidencia.
    """

    run_id: UUID
    evidence_id: UUID
    dataset_id: str
    canonical_soql: str
    rows: tuple[Mapping[str, JsonValue], ...]
    eligibility_status: TextualEligibilityStatus
    quality_classification: TextualQualityClassification
    validated_order_is_total: bool = False

    def __post_init__(self) -> None:
        frozen_rows = tuple(MappingProxyType(copy.deepcopy(dict(row))) for row in self.rows)
        object.__setattr__(self, "rows", frozen_rows)

    def to_operation_evidence(self) -> TextualEvidence:
        return TextualEvidence(
            dataset_id=self.dataset_id,
            canonical_soql=self.canonical_soql,
            rows=self.rows,
            validated_order_is_total=self.validated_order_is_total,
        )


@dataclass(frozen=True, slots=True)
class TextualFactBuildCommand:
    evidence_id: UUID
    dataset_id: str
    spec: TextualFactSpec
    validated_order_is_total: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedTextualFact:
    """Marca interna que solo puede producir el verificador independiente."""

    fact: TextualFact


def render_textual_fact(result: TextualOperationResult) -> str:
    """Renderiza el texto cerrado de una operación sin aceptar prosa externa."""

    try:
        template = TEXTUAL_FACT_TEMPLATES[result.operation]
    except KeyError as exc:
        raise TextualFactError(
            "textual_unknown_operation",
            "no existe una plantilla cerrada para la operación textual",
        ) from exc
    return template.format(display_value=result.display_value)


def build_textual_fact(
    *,
    run_id: UUID,
    evidence_id: UUID,
    dataset_id: str,
    snapshot: TextualEvidenceSnapshot | None,
    spec: TextualFactSpec,
    fact_id_factory: FactIdFactory = uuid.uuid4,
) -> TextualFact:
    """Construye un hecho solo desde evidencia elegible y T-615D."""

    _require_textual_spec(spec)
    _validate_snapshot_reference(
        run_id=run_id,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        snapshot=snapshot,
    )
    assert snapshot is not None  # estrechado por _validate_snapshot_reference
    result = _evaluate(snapshot, spec)
    fact_id = fact_id_factory()
    if not isinstance(fact_id, UUID):
        raise TextualFactError(
            "textual_invalid_fact_id",
            "el generador de fact_id debe devolver un UUID",
        )
    return TextualFact(
        fact_id=fact_id,
        fact_kind=TextualFactKind.TEXTUAL,
        fact=render_textual_fact(result),
        operation=result.operation,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        source_row_indexes=result.source_row_indexes,
        columns=result.columns,
        raw_values=result.raw_values,
        normalized_values=result.normalized_values,
        display_value=result.display_value,
        normalization_profile=result.normalization_profile,
        operation_params=result.operation_params,
        algorithm_version=result.algorithm_version,
        source_hash=result.source_hash,
    )


def verify_textual_fact(
    *,
    run_id: UUID,
    evidence_id: UUID,
    dataset_id: str,
    snapshot: TextualEvidenceSnapshot | None,
    spec: TextualFactSpec,
    fact: TextualFact,
) -> VerifiedTextualFact:
    """Recomputa de manera independiente y rechaza, sin corregir, diferencias."""

    _require_textual_spec(spec)
    _validate_snapshot_reference(
        run_id=run_id,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        snapshot=snapshot,
    )
    assert snapshot is not None

    _require_equal(
        fact.fact_kind,
        TextualFactKind.TEXTUAL,
        "textual_fact_kind_mismatch",
        "fact_kind no corresponde a un hecho textual",
    )
    _require_equal(
        fact.evidence_id,
        evidence_id,
        "textual_evidence_mismatch",
        "evidence_id del hecho fue alterado",
    )
    _require_equal(
        fact.dataset_id,
        dataset_id,
        "textual_dataset_mismatch",
        "dataset_id del hecho fue alterado",
    )
    _require_equal(
        fact.operation,
        spec.operation,
        "textual_operation_mismatch",
        "la operación del hecho no coincide con la especificación",
    )

    result = _evaluate(snapshot, spec)
    expected = (
        (
            fact.source_row_indexes,
            result.source_row_indexes,
            "textual_source_rows_mismatch",
            "los índices fuente del hecho fueron alterados",
        ),
        (
            fact.columns,
            result.columns,
            "textual_columns_mismatch",
            "las columnas del hecho fueron alteradas",
        ),
        (
            fact.raw_values,
            result.raw_values,
            "textual_raw_values_mismatch",
            "los valores fuente del hecho fueron alterados",
        ),
        (
            fact.normalized_values,
            result.normalized_values,
            "textual_normalized_values_mismatch",
            "los valores normalizados del hecho fueron alterados",
        ),
        (
            fact.display_value,
            result.display_value,
            "textual_display_value_mismatch",
            "la presentación del hecho fue alterada",
        ),
        (
            fact.normalization_profile,
            result.normalization_profile,
            "textual_normalization_profile_mismatch",
            "el perfil de normalización del hecho fue alterado",
        ),
        (
            fact.operation_params,
            result.operation_params,
            "textual_operation_params_mismatch",
            "los parámetros de operación del hecho fueron alterados",
        ),
        (
            fact.algorithm_version,
            result.algorithm_version,
            "textual_algorithm_version_mismatch",
            "la versión del algoritmo del hecho fue alterada",
        ),
        (
            fact.source_hash,
            result.source_hash,
            "textual_source_hash_mismatch",
            "el hash del hecho no coincide con la recomputación",
        ),
        (
            fact.fact,
            render_textual_fact(result),
            "textual_fact_text_mismatch",
            "el texto determinista del hecho fue alterado",
        ),
    )
    for actual, recomputed, code, message in expected:
        _require_equal(actual, recomputed, code, message)
    return VerifiedTextualFact(fact=fact)


def _require_textual_spec(spec: object) -> None:
    if isinstance(spec, TextualFactSpec):
        return
    if _looks_like_quantitative_substitute(spec):
        raise TextualFactError(
            "textual_quantitative_substitute",
            "un hecho textual no admite count, raw_value, fórmula, unidad o redondeo",
        )
    raise TextualFactError(
        "textual_invalid_spec",
        "la especificación no pertenece al contrato TextualFactSpec",
    )


def _looks_like_quantitative_substitute(value: object) -> bool:
    if isinstance(value, Mapping):
        return bool(_QUANTITATIVE_MARKERS.intersection(value))
    return any(hasattr(value, marker) for marker in _QUANTITATIVE_MARKERS)


def _validate_snapshot_reference(
    *,
    run_id: UUID,
    evidence_id: UUID,
    dataset_id: str,
    snapshot: TextualEvidenceSnapshot | None,
) -> None:
    if snapshot is None:
        raise TextualFactError(
            "textual_evidence_not_found",
            "la evidencia solicitada no existe",
        )
    if snapshot.evidence_id != evidence_id:
        raise TextualFactError(
            "textual_evidence_mismatch",
            "el snapshot no corresponde al evidence_id solicitado",
        )
    if snapshot.run_id != run_id:
        raise TextualFactError(
            "textual_evidence_run_mismatch",
            "la evidencia pertenece a otra corrida",
        )
    if snapshot.dataset_id != dataset_id:
        raise TextualFactError(
            "textual_dataset_mismatch",
            "el dataset solicitado no coincide con la evidencia",
        )
    if not snapshot.rows:
        raise TextualFactError(
            "textual_evidence_rows_unverifiable",
            "la evidencia no contiene filas verificables",
        )
    if snapshot.eligibility_status == "blocked":
        raise TextualFactError(
            "textual_evidence_blocked",
            "la evidencia está bloqueada y no puede producir hechos entregables",
        )
    if snapshot.eligibility_status == "diagnostic_only":
        raise TextualFactError(
            "textual_evidence_diagnostic_only",
            "la evidencia es solo diagnóstica y no puede producir hechos entregables",
        )
    if snapshot.eligibility_status != "eligible":
        raise TextualFactError(
            "textual_evidence_not_eligible",
            "la evidencia no tiene un estado de elegibilidad reconocido",
        )
    if snapshot.quality_classification == "no_recomendada":
        raise TextualFactError(
            "textual_evidence_not_recommended",
            "la calidad de la evidencia está clasificada como no recomendada",
        )
    if snapshot.quality_classification not in {"alta", "media", "baja"}:
        raise TextualFactError(
            "textual_evidence_not_eligible",
            "la evidencia no tiene una clasificación de calidad reconocida",
        )


def _evaluate(
    snapshot: TextualEvidenceSnapshot,
    spec: TextualFactSpec,
) -> TextualOperationResult:
    try:
        return evaluate_textual_operation(
            evidence=snapshot.to_operation_evidence(),
            spec=spec,
        )
    except TextualOperationError as exc:
        raise TextualFactError(exc.code, str(exc)) from exc


def _require_equal(
    actual: object,
    expected: object,
    code: str,
    message: str,
) -> None:
    if actual != expected:
        raise TextualFactError(code, message)
