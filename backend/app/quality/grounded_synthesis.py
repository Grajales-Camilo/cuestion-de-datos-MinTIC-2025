"""Validación y renderizado literal de síntesis fundamentada (T-615H, RF-210).

El LLM puede ordenar referencias y elegir conectores o plantillas cerradas,
pero este módulo conserva toda la autoridad sobre pertenencia, compatibilidad
y texto final. No consulta red ni base de datos y no modifica hechos.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.quality.claim_labels import LabelStatus, claim_is_relevant_to_narrative
from app.quality.grounded_facts import (
    GroundedSynthesisClosing,
    GroundedSynthesisConnector,
    GroundedSynthesisPlan,
    GroundedSynthesisSegment,
    GroundedSynthesisTemplate,
    QuantitativeFactKind,
    TextualFactKind,
)


class GroundedSynthesisValidationError(ValueError):
    """El plan no puede certificarse contra los hechos permitidos."""


class _AllowedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    run_id: UUID
    evidence_id: UUID
    dataset_id: str = Field(pattern=r"^[a-z0-9]{4}-[a-z0-9]{4}$")
    source_row_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)
    columns: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    source_hash: str
    quality_classification: Literal["alta", "media", "baja"]

    @model_validator(mode="after")
    def _validate_canonical_coordinates(self) -> _AllowedFact:
        if tuple(sorted(set(self.source_row_indexes))) != self.source_row_indexes:
            raise ValueError("source_row_indexes debe ser canónico")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns no admite duplicados")
        return self


class AllowedQuantitativeFact(_AllowedFact):
    fact_kind: Literal[QuantitativeFactKind.QUANTITATIVE] = QuantitativeFactKind.QUANTITATIVE
    source_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    claim: str = Field(min_length=1)
    display_value: str = Field(min_length=1)
    #: RF-212 (T-617C-R1): etiqueta humana verificable derivada de
    #: `columns` (nombre de columna fuente real), o `None` si
    #: `label_status="ambiguous"`. Nunca se infiere del valor numérico.
    label: str | None = None
    label_status: LabelStatus = "ambiguous"


class AllowedTextualFact(_AllowedFact):
    fact_kind: Literal[TextualFactKind.TEXTUAL] = TextualFactKind.TEXTUAL
    source_hash: str = Field(pattern=r"^sha256-jcs-v1:[0-9a-f]{64}$")
    fact: str = Field(min_length=1)
    display_value: str | None = None
    label: str | None = None
    label_status: LabelStatus = "ambiguous"


AllowedGroundedFact = Annotated[
    AllowedQuantitativeFact | AllowedTextualFact,
    Field(discriminator="fact_kind"),
]


class AllowedGroundedFacts(BaseModel):
    """Conjunto cerrado cargado y reverificado para una única corrida."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    facts: tuple[AllowedGroundedFact, ...]

    @model_validator(mode="after")
    def _validate_run_and_identities(self) -> AllowedGroundedFacts:
        identities: set[tuple[QuantitativeFactKind | TextualFactKind, UUID]] = set()
        for fact in self.facts:
            if fact.run_id != self.run_id:
                raise ValueError("todos los hechos permitidos deben pertenecer a la corrida")
            identity = (fact.fact_kind, fact.id)
            if identity in identities:
                raise ValueError("un hecho permitido no puede repetirse")
            identities.add(identity)
        return self

    def by_identity(
        self,
    ) -> dict[
        tuple[QuantitativeFactKind | TextualFactKind, UUID],
        AllowedQuantitativeFact | AllowedTextualFact,
    ]:
        return {(fact.fact_kind, fact.id): fact for fact in self.facts}


_CONNECTOR_TEXT = {
    GroundedSynthesisConnector.SIN_CONECTOR: "",
    GroundedSynthesisConnector.ADEMAS: "Además, ",
    GroundedSynthesisConnector.POR_OTRA_PARTE: "Por otra parte, ",
    GroundedSynthesisConnector.EN_CONJUNTO: "En conjunto, ",
}

_CLOSING_TEXT = {
    GroundedSynthesisClosing.SIN_CIERRE: "",
    GroundedSynthesisClosing.LIMITACION_DISPONIBILIDAD: (
        " La respuesta se limita a la evidencia disponible."
    ),
    GroundedSynthesisClosing.ADVERTENCIA_CALIDAD: (
        " La evidencia utilizada presenta una advertencia de calidad."
    ),
}


def validate_grounded_synthesis_plan(
    plan: GroundedSynthesisPlan,
    allowed: AllowedGroundedFacts,
) -> None:
    """Certifica referencias, conectores y comparaciones contra una corrida."""

    facts_by_identity = allowed.by_identity()
    resolved_by_segment: list[tuple[AllowedQuantitativeFact | AllowedTextualFact, ...]] = []
    for index, segment in enumerate(plan.segments):
        if index == 0 and segment.connector is not GroundedSynthesisConnector.SIN_CONECTOR:
            raise GroundedSynthesisValidationError(
                "el primer segmento debe usar el conector sin_conector"
            )
        if index > 0 and segment.connector is GroundedSynthesisConnector.SIN_CONECTOR:
            raise GroundedSynthesisValidationError(
                "los segmentos posteriores deben usar un conector explícito"
            )

        resolved: list[AllowedQuantitativeFact | AllowedTextualFact] = []
        for reference in segment.fact_refs:
            fact = facts_by_identity.get((reference.fact_kind, reference.id))
            if fact is None:
                raise GroundedSynthesisValidationError(
                    f"referencia no autorizada: {reference.fact_kind.value}:{reference.id}"
                )
            if fact.run_id != allowed.run_id:
                raise GroundedSynthesisValidationError(
                    "la referencia no pertenece a la corrida autorizada"
                )
            resolved.append(fact)

        if segment.template is GroundedSynthesisTemplate.COMPARISON_PAIR:
            first, second = resolved
            if first.evidence_id != second.evidence_id:
                raise GroundedSynthesisValidationError(
                    "comparison_pair requiere hechos de la misma evidencia"
                )
        resolved_by_segment.append(tuple(resolved))

    if not resolved_by_segment:
        raise GroundedSynthesisValidationError("el plan no contiene segmentos")


def render_grounded_synthesis(
    plan: GroundedSynthesisPlan,
    allowed: AllowedGroundedFacts,
) -> str:
    """Renderiza exclusivamente literales aprobados y valores persistidos."""

    validate_grounded_synthesis_plan(plan, allowed)
    facts_by_identity = allowed.by_identity()
    rendered_segments: list[str] = []
    for segment in plan.segments:
        facts = tuple(
            facts_by_identity[(reference.fact_kind, reference.id)]
            for reference in segment.fact_refs
        )
        atomic_clauses = tuple(_atomic_clause(fact) for fact in facts)
        rendered_segments.append(
            _CONNECTOR_TEXT[segment.connector] + _render_template(segment.template, atomic_clauses)
        )
    return " ".join(rendered_segments) + _CLOSING_TEXT[plan.closing]


def build_grounded_synthesis_fallback(
    allowed: AllowedGroundedFacts,
    *,
    requested_tokens: frozenset[str] = frozenset(),
) -> GroundedSynthesisPlan:
    """Construye el plan determinista cerrado cuando el plan LLM no es usable.

    RF-212 (T-617C-R1): prioriza hechos cuantitativos relevantes para la
    intención (mismo criterio genérico que la ruta con LLM y el fallback
    del contrato antiguo); los hechos textuales no tienen noción de columna
    auxiliar/temporal y siempre se conservan elegibles."""

    if not allowed.facts:
        raise GroundedSynthesisValidationError(
            "no hay ningún hecho permitido para construir fallback"
        )
    relevant = [
        fact
        for fact in allowed.facts
        if not isinstance(fact, AllowedQuantitativeFact)
        or claim_is_relevant_to_narrative(fact.columns, requested_tokens=requested_tokens)
    ]
    pool = relevant if relevant else list(allowed.facts)
    ordered = sorted(pool, key=_fallback_sort_key)
    selected = ordered[:8]
    if len(ordered) > 8:
        closing = GroundedSynthesisClosing.LIMITACION_DISPONIBILIDAD
    elif any(fact.quality_classification == "baja" for fact in selected):
        closing = GroundedSynthesisClosing.ADVERTENCIA_CALIDAD
    else:
        closing = GroundedSynthesisClosing.SIN_CIERRE

    segments = tuple(
        GroundedSynthesisSegment.model_validate(
            {
                "segment_id": f"fallback-{index + 1}",
                "connector": (
                    GroundedSynthesisConnector.SIN_CONECTOR
                    if index == 0
                    else GroundedSynthesisConnector.ADEMAS
                ),
                "template": GroundedSynthesisTemplate.FACT_STATEMENT,
                "fact_refs": [
                    {
                        "fact_kind": fact.fact_kind,
                        "id": fact.id,
                    }
                ],
            }
        )
        for index, fact in enumerate(selected)
    )
    plan = GroundedSynthesisPlan(segments=segments, closing=closing)
    validate_grounded_synthesis_plan(plan, allowed)
    return plan


def _atomic_clause(fact: AllowedQuantitativeFact | AllowedTextualFact) -> str:
    if isinstance(fact, AllowedQuantitativeFact):
        # RF-212: etiqueta humana verificable en vez del `claim`/alias
        # crudo; ambiguo se señala explícitamente, nunca se inventa.
        if fact.label_status == "verified" and fact.label:
            return f"{fact.label}: {fact.display_value}."
        return f"{fact.display_value} (sin etiqueta verificable)."
    if (
        isinstance(fact, AllowedTextualFact)
        and fact.label_status == "verified"
        and fact.label
        and fact.display_value
    ):
        return f"{fact.label}: {fact.display_value}."
    return fact.fact


def _render_template(
    template: GroundedSynthesisTemplate,
    atomic_clauses: tuple[str, ...],
) -> str:
    if template is GroundedSynthesisTemplate.FACT_STATEMENT:
        return atomic_clauses[0]
    if template is GroundedSynthesisTemplate.SUBJECT_FACT:
        return f"Resultado verificado: {atomic_clauses[0]}"
    return f"Resultados relacionados: {atomic_clauses[0]} {atomic_clauses[1]}"


def _fallback_sort_key(
    fact: AllowedQuantitativeFact | AllowedTextualFact,
) -> tuple[int, str, tuple[int, ...], tuple[str, ...], str]:
    return (
        0 if isinstance(fact, AllowedQuantitativeFact) else 1,
        fact.dataset_id,
        fact.source_row_indexes,
        fact.columns,
        fact.source_hash,
    )
