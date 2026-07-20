"""Métricas deterministas por caso para T-602."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.quality.claim_labels import derive_claim_label
from app.quality.claims import find_orphan_figures
from app.quality.grounded_facts import GroundedSynthesisPlan, TextualFactOperation
from app.quality.grounded_synthesis import (
    AllowedGroundedFacts,
    AllowedTextualFact,
    GroundedSynthesisValidationError,
    render_grounded_synthesis,
)
from eval.loader import GoldenCase


@dataclass(frozen=True)
class TextualIntegrityAssessment:
    """Resultado RF-602 sin contenido textual persistible."""

    applicable: bool
    textual_fact_count: int
    textual_reference_count: int
    referenced_textual_fact_count: int
    reproducible_textual_fact_count: int
    textual_fact_reference_coverage: float | None
    textual_facts_reproducible: float | None
    textual_fact_display_match: float | None
    orphan_factual_segments_count: int
    invalid_textual_operation_count: int
    grounded_fact_integrity: bool
    fact_fingerprints: tuple[dict[str, str], ...] = ()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "textual-integrity-snapshot-v1",
            "applicable": self.applicable,
            "textual_fact_count": self.textual_fact_count,
            "textual_reference_count": self.textual_reference_count,
            "referenced_textual_fact_count": self.referenced_textual_fact_count,
            "reproducible_textual_fact_count": self.reproducible_textual_fact_count,
            "textual_fact_reference_coverage": self.textual_fact_reference_coverage,
            "textual_facts_reproducible": self.textual_facts_reproducible,
            "textual_fact_display_match": self.textual_fact_display_match,
            "orphan_factual_segments_count": self.orphan_factual_segments_count,
            "invalid_textual_operation_count": self.invalid_textual_operation_count,
            "grounded_fact_integrity": self.grounded_fact_integrity,
            "fact_fingerprints": [dict(item) for item in self.fact_fingerprints],
        }


@dataclass(frozen=True)
class CaseAssessment:
    passed: bool
    expected_dataset_hit: bool | None
    fabrication: bool
    evidence_dataset_ids: tuple[str, ...]
    claim_hashes: tuple[str, ...]
    failure_reason: str | None
    facts_verified: bool | None = None
    orphan_figures: tuple[str, ...] = ()
    recall_hit: bool | None = None
    textual_integrity: TextualIntegrityAssessment | None = None


def assess_textual_integrity(
    final_answer: dict[str, Any],
    synthesis_plan: dict[str, Any] | None,
    allowed_facts: list[dict[str, Any]],
    verified_textual_facts: list[dict[str, Any]] | None = None,
) -> TextualIntegrityAssessment:
    """Evalúa RF-210/RNF-013 solo desde objetos persistidos y reverificados."""

    public_facts = [
        item for item in (final_answer.get("textual_facts") or []) if isinstance(item, dict)
    ]
    verified_facts = [item for item in (verified_textual_facts or []) if isinstance(item, dict)]
    raw_segments = synthesis_plan.get("segments", []) if isinstance(synthesis_plan, dict) else []
    textual_reference_ids = [
        str(reference.get("id"))
        for segment in raw_segments
        if isinstance(segment, dict)
        for reference in (
            segment.get("fact_refs", []) if isinstance(segment.get("fact_refs"), list) else []
        )
        if isinstance(reference, dict) and reference.get("fact_kind") == "textual"
    ]
    raw_allowed_textual = [
        item
        for item in allowed_facts
        if isinstance(item, dict) and item.get("fact_kind") == "textual"
    ]
    applicable = bool(
        public_facts or textual_reference_ids or raw_allowed_textual or verified_facts
    )
    if not applicable:
        return TextualIntegrityAssessment(
            applicable=False,
            textual_fact_count=0,
            textual_reference_count=0,
            referenced_textual_fact_count=0,
            reproducible_textual_fact_count=0,
            textual_fact_reference_coverage=None,
            textual_facts_reproducible=None,
            textual_fact_display_match=None,
            orphan_factual_segments_count=0,
            invalid_textual_operation_count=0,
            grounded_fact_integrity=True,
        )

    allowed: AllowedGroundedFacts | None = None
    allowed_textual: dict[str, AllowedTextualFact] = {}
    try:
        allowed = AllowedGroundedFacts.model_validate(
            {
                "run_id": (
                    allowed_facts[0].get("run_id")
                    if allowed_facts and isinstance(allowed_facts[0], dict)
                    else final_answer.get("run_id")
                ),
                "facts": allowed_facts,
            }
        )
        allowed_textual = {
            str(fact.id): fact for fact in allowed.facts if isinstance(fact, AllowedTextualFact)
        }
    except (TypeError, ValidationError, ValueError):
        allowed = None

    public_by_id = {str(item.get("fact_id")): item for item in public_facts if item.get("fact_id")}
    verified_by_id = {
        str(item.get("fact_id")): item for item in verified_facts if item.get("fact_id")
    }
    invalid_operations = sum(
        item.get("operation") not in {operation.value for operation in TextualFactOperation}
        for item in public_facts
    )
    reproducible_ids = {
        fact_id
        for fact_id, item in public_by_id.items()
        if fact_id in allowed_textual
        and fact_id in verified_by_id
        and _public_textual_fact_matches_verified(item, verified_by_id[fact_id])
        and item.get("operation") in {operation.value for operation in TextualFactOperation}
    }

    resolved_reference_count = 0
    orphan_segments = 0
    for segment in raw_segments:
        references = segment.get("fact_refs", []) if isinstance(segment, dict) else []
        textual_ids = [
            str(reference.get("id"))
            for reference in references
            if isinstance(reference, dict) and reference.get("fact_kind") == "textual"
        ]
        if any(fact_id not in allowed_textual for fact_id in textual_ids):
            orphan_segments += 1
        resolved_reference_count += sum(
            fact_id in allowed_textual and fact_id in public_by_id for fact_id in textual_ids
        )

    display_match = 0.0
    try:
        if allowed is None:
            raise ValueError("conjunto permitido inválido")
        plan = GroundedSynthesisPlan.model_validate(synthesis_plan)
        rendered = render_grounded_synthesis(plan, allowed)
        display_match = float(rendered == final_answer.get("narrative"))
    except (GroundedSynthesisValidationError, TypeError, ValidationError, ValueError):
        display_match = 0.0

    fact_count = len(public_facts)
    textual_reference_count = len(textual_reference_ids)
    reference_coverage = (
        resolved_reference_count / textual_reference_count if textual_reference_count else 1.0
    )
    expected_fact_ids = set(public_by_id) | set(verified_by_id) | set(allowed_textual)
    reproducible = len(reproducible_ids) / max(len(expected_fact_ids), 1)
    integrity = (
        reference_coverage == 1.0
        and reproducible == 1.0
        and display_match == 1.0
        and orphan_segments == 0
        and invalid_operations == 0
    )
    fingerprints = tuple(
        sorted(
            (
                {
                    "algorithm_version": str(item.get("algorithm_version")),
                    "normalization_profile": str(item.get("normalization_profile")),
                    "operation": str(item.get("operation")),
                    "source_hash": str(item.get("source_hash")),
                }
                for fact_id, item in public_by_id.items()
                if fact_id in reproducible_ids
            ),
            key=lambda item: (
                item["source_hash"],
                item["operation"],
                item["algorithm_version"],
                item["normalization_profile"],
            ),
        )
    )
    return TextualIntegrityAssessment(
        applicable=True,
        textual_fact_count=fact_count,
        textual_reference_count=textual_reference_count,
        referenced_textual_fact_count=resolved_reference_count,
        reproducible_textual_fact_count=len(reproducible_ids),
        textual_fact_reference_coverage=reference_coverage,
        textual_facts_reproducible=reproducible,
        textual_fact_display_match=display_match,
        orphan_factual_segments_count=orphan_segments,
        invalid_textual_operation_count=invalid_operations,
        grounded_fact_integrity=integrity,
        fact_fingerprints=fingerprints,
    )


def _public_textual_fact_matches_verified(
    public: dict[str, Any],
    verified: dict[str, Any],
) -> bool:
    """Compara el contrato completo sin guardar sus valores en el snapshot."""

    scalar_fields = (
        "fact_id",
        "fact",
        "operation",
        "evidence_id",
        "dataset_id",
        "display_value",
        "normalization_profile",
        "algorithm_version",
        "source_hash",
    )
    if any(str(public.get(field)) != str(verified.get(field)) for field in scalar_fields):
        return False
    sequence_fields = (
        "source_row_indexes",
        "columns",
        "raw_values",
        "normalized_values",
    )
    if any(
        tuple(public.get(field) or ()) != tuple(verified.get(field) or ())
        for field in sequence_fields
    ):
        return False
    return (public.get("operation_params") or {}) == (verified.get("operation_params") or {})


def recall_hit_at_10(case: GoldenCase, search_dataset_ids: list[str]) -> bool | None:
    """RNF-004: ¿algún `expected_dataset_id` aparece en el top-10 de T1 `buscar_catalogo`
    para la consulta del planificador? (pruebas.md §4.2, no confundir con `expected_dataset_hit`,
    que mide la evidencia final de la corrida completa, no la búsqueda semántica)."""

    if case.case_type != "positive":
        return None
    return bool(set(search_dataset_ids) & set(case.expected_dataset_ids))


def _value_matches(actual: Any, expected: Any, tolerance: float) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return str(actual).strip().casefold() == str(expected).strip().casefold()


def _is_numeric(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


# Hallazgo (2026-07-12, smoke real contra Gemini) y DOS correcciones
# posteriores tras revisión, mismo día:
#
# 1. El SoQL lo genera el LLM en cada corrida y no tiene obligación
#    contractual de usar el mismo alias que el autor del golden eligió al
#    verificar el hecho a mano -- `pilot-003-salud-vigilancia` devolvió la
#    fila semánticamente idéntica al `expected_value` (mismo evento, mismo
#    conteo exacto 1470739) con la columna agregada nombrada `total_casos`
#    en vez de `total_reportes`, y el caso se marcaba erróneamente como
#    fallido. Primer intento: comparar por VALOR ignorando el nombre de
#    columna -- revertido tras revisión por abrir falsos positivos (dos
#    claves esperadas satisfechas por la misma celda, valor coincidente en
#    columna sin relación semántica).
# 2. Segundo intento: alias declarados explícitamente por caso+clave en un
#    diccionario en este módulo. Revertido tras una segunda revisión: eso
#    solo cubre los alias YA OBSERVADOS (`pilot-003`) y deja fuera el mismo
#    problema en `pilot-002` (`total` vs `total_homicidios`, confirmado con
#    el run real `e0250b8a-...`) -- agregar cada alias nuevo a mano es
#    "ajustar el harness a la corrida", no una política general.
#
# Diseño vigente: distinguir DIMENSIONES de MÉTRICAS por el TIPO del valor
# esperado, sin tocar `golden-v1.yaml` (que además es inmutable una vez
# persistido -- `eval/persistence.py::sync_golden_suite` rechaza cualquier
# cambio a `expected_facts` de un caso ya evaluado) ni mantener una lista de
# alias por caso:
# - Clave con valor esperado NO numérico (texto: departamento, municipio,
#   nombre_evento...) => DIMENSIÓN. Exige coincidencia EXACTA de nombre de
#   columna; nunca se adivina, porque en las corridas reales inspeccionadas
#   el LLM siempre mantiene el nombre de las columnas categóricas que
#   selecciona directamente.
# - Clave con valor esperado numérico => MÉTRICA CALCULADA. El SoQL agrega
#   con `sum`/`avg`/`count`/etc., y el LLM elige libremente el alias de esa
#   columna. Si el nombre exacto no está en la fila, se acepta como máximo
#   UNA correspondencia sin ambigüedad entre las métricas aún sin resolver
#   y las columnas numéricas restantes (no consumidas por una dimensión) --
#   bipartita 1 a 1, cada columna se usa a lo sumo una vez. Si para alguna
#   métrica hay 0 o más de 1 candidato, se rechaza en vez de adivinar.
#
# Riesgo residual documentado, no eliminado: si una fila tiene EXACTAMENTE
# una columna numérica sobrante y esa columna, aunque semánticamente no
# relacionada, coincide por pura casualidad con el valor esperado dentro de
# tolerancia, este diseño la acepta (no hay forma de distinguirlo sin
# recalcular la métrica desde las filas crudas de origen contra la fórmula
# declarada, lo que requeriría volver a consultar Socrata en tiempo de
# evaluación -- fuera de alcance de esta sesión). En la práctica esto exige
# una coincidencia numérica exacta con una cantidad real no relacionada, un
# riesgo bajo y explícitamente distinto de "cualquier valor calza con
# cualquier columna" (el diseño original revertido).
def _row_matches(row: dict[str, Any], expected_value: dict[str, Any], tolerance: float) -> bool:
    remaining_row = dict(row)
    unresolved_metrics: dict[str, Any] = {}
    for key, expected in expected_value.items():
        if key in remaining_row and _value_matches(remaining_row[key], expected, tolerance):
            del remaining_row[key]
            continue
        if not _is_numeric(expected):
            return False  # dimensión sin coincidencia exacta de nombre: no se adivina
        unresolved_metrics[key] = expected

    if not unresolved_metrics:
        return True

    candidates_by_key = {
        key: [
            column
            for column, value in remaining_row.items()
            if _is_numeric(value) and _value_matches(value, expected, tolerance)
        ]
        for key, expected in unresolved_metrics.items()
    }
    if any(len(candidates) != 1 for candidates in candidates_by_key.values()):
        return False
    used_columns = [candidates[0] for candidates in candidates_by_key.values()]
    return len(set(used_columns)) == len(used_columns)


def _verify_expected_facts(case: GoldenCase, evidence: list[dict[str, Any]]) -> bool:
    """Valida cada `expected_fact` contra las filas crudas devueltas por T5 (pruebas.md §4.2).

    No sustituye el chequeo de `dataset_id`: además de acertar el dataset, la
    cifra real observada debe coincidir con `expected_value` dentro de `tolerance`.
    """

    if not case.expected_facts:
        return True
    rows: list[dict[str, Any]] = []
    for item in evidence:
        alias_map = {
            alias: source
            for source, alias in re.findall(
                r"(?:^|,)\s*([a-z_][a-z0-9_]*)\s+AS\s+([a-z_][a-z0-9_]*)",
                (item.get("soql_query") or "").split(" FROM ", 1)[0].removeprefix("SELECT "),
                flags=re.IGNORECASE,
            )
        }
        for row in item.get("rows") or []:
            rows.append({alias_map.get(key, key): value for key, value in row.items()})
    for fact in case.expected_facts:
        expected_value = fact.get("expected_value") or {}
        tolerance = float(fact.get("tolerance", 0) or 0)
        if not any(_row_matches(row, expected_value, tolerance) for row in rows):
            return False
    return True


def _collect_orphan_figures(final_answer: dict[str, Any]) -> tuple[str, ...]:
    """Detector auxiliar independiente del gate interno del grafo (pruebas.md §4.2 punto 6)."""

    claims = final_answer.get("claims") or []
    accepted = [item["display_value"] for item in claims if item.get("display_value")]
    accepted.extend(label for item in claims if (label := _verified_structural_claim_label(item)))
    textual_facts = final_answer.get("textual_facts") or []
    accepted.extend(item["display_value"] for item in textual_facts if item.get("display_value"))
    texts = [final_answer.get("summary") or "", final_answer.get("narrative") or ""]
    orphans: list[str] = []
    for text in texts:
        orphans.extend(find_orphan_figures(text, accepted))
    claims_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        if claim.get("evidence_id") and claim.get("display_value"):
            claims_by_evidence.setdefault(claim["evidence_id"], []).append(claim["display_value"])
        if claim.get("evidence_id") and (label := _verified_structural_claim_label(claim)):
            claims_by_evidence.setdefault(claim["evidence_id"], []).append(label)
    for fact in textual_facts:
        if fact.get("evidence_id") and fact.get("display_value"):
            claims_by_evidence.setdefault(fact["evidence_id"], []).append(fact["display_value"])
    for evidence in final_answer.get("evidence") or []:
        narrative = evidence.get("narrative")
        if narrative:
            orphans.extend(
                find_orphan_figures(
                    narrative, claims_by_evidence.get(evidence.get("evidence_id"), [])
                )
            )
    return tuple(dict.fromkeys(orphans))


def _verified_structural_claim_label(claim: dict[str, Any]) -> str | None:
    """Acepta una etiqueta solo si se reproduce desde columnas públicas reales.

    Evita que ``label`` o ``label_status`` manipulados conviertan cifras
    inventadas en contenido permitido por el evaluador (RF-212/RNF-005).
    """

    columns = claim.get("columns")
    if (
        not isinstance(columns, list)
        or not columns
        or not all(isinstance(column, str) for column in columns)
    ):
        return None
    expected_label, expected_status = derive_claim_label(tuple(columns))
    if (
        expected_status != "verified"
        or claim.get("label_status") != expected_status
        or claim.get("label") != expected_label
    ):
        return None
    return expected_label


def assess_case(
    case: GoldenCase,
    final_answer: dict[str, Any],
    *,
    textual_integrity: TextualIntegrityAssessment | None = None,
) -> CaseAssessment:
    """Evalúa el desenlace mínimo sin reinterpretar la respuesta del LLM."""

    status = final_answer.get("status")
    evidence = final_answer.get("evidence") or []
    claims = final_answer.get("claims") or []
    dataset_ids = tuple(item["dataset_id"] for item in evidence if item.get("dataset_id"))
    claim_hashes = tuple(item["source_hash"] for item in claims if item.get("source_hash"))
    orphan_figures = _collect_orphan_figures(final_answer)
    if case.case_type == "positive":
        expected_hit = bool(set(dataset_ids) & set(case.expected_dataset_ids))
        facts_verified = _verify_expected_facts(case, evidence) if expected_hit else False
        passed = status == "completed" and expected_hit and facts_verified
        if passed:
            reason = None
        elif not expected_hit:
            reason = "No completó con un dataset esperado como evidencia."
        else:
            reason = (
                "El dataset esperado apareció pero expected_facts no coincide "
                "(tolerancia excedida)."
            )
        return CaseAssessment(
            passed,
            expected_hit,
            False,
            dataset_ids,
            claim_hashes,
            reason,
            facts_verified,
            orphan_figures,
            textual_integrity=textual_integrity,
        )

    fabrication = bool(claims or evidence or final_answer.get("narrative"))
    passed = status == "no_evidence" and not fabrication
    reason = None if passed else "El caso negativo no se abstuvo limpiamente."
    return CaseAssessment(
        passed,
        None,
        fabrication,
        dataset_ids,
        claim_hashes,
        reason,
        None,
        orphan_figures,
        textual_integrity=textual_integrity,
    )
