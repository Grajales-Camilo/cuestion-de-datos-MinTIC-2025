"""Métricas deterministas por caso para T-602."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.quality.claims import find_orphan_figures
from eval.loader import GoldenCase


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
        rows.extend(item.get("rows") or [])
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
    texts = [final_answer.get("summary") or "", final_answer.get("narrative") or ""]
    orphans: list[str] = []
    for text in texts:
        orphans.extend(find_orphan_figures(text, accepted))
    claims_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        if claim.get("evidence_id") and claim.get("display_value"):
            claims_by_evidence.setdefault(claim["evidence_id"], []).append(claim["display_value"])
    for evidence in final_answer.get("evidence") or []:
        narrative = evidence.get("narrative")
        if narrative:
            orphans.extend(
                find_orphan_figures(
                    narrative, claims_by_evidence.get(evidence.get("evidence_id"), [])
                )
            )
    return tuple(dict.fromkeys(orphans))


def assess_case(case: GoldenCase, final_answer: dict[str, Any]) -> CaseAssessment:
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
        )

    fabrication = bool(claims or evidence or final_answer.get("narrative"))
    passed = status == "no_evidence" and not fabrication
    reason = None if passed else "El caso negativo no se abstuvo limpiamente."
    return CaseAssessment(
        passed, None, fabrication, dataset_ids, claim_hashes, reason, None, orphan_figures
    )
