"""Instrumentación de la puerta de evaluación OE3 (T-617B0).

Módulo PURO: sin I/O, sin LLM, sin acceso a base de datos ni a Socrata. Todas
las funciones operan sobre objetos ya materializados por el runner
(``final_answer`` persistido, diagnósticos por etapa y observaciones de paso) y
son deterministas y probables sin cuota de modelo.

Cierra los huecos reproducidos en T-617B0:

- El ``success_rate`` de la puerta se calcula SOLO sobre casos positivos; los
  negativos se contabilizan por separado y exigen 100% (RNF-002/RNF-005,
  pruebas.md §4.2/§4.4).
- La integridad cuantitativa (RF-208/RNF-003) se reejecuta de forma
  determinista desde la evidencia persistida, no se sustituye por
  ``expected_facts`` ni por prosa del LLM.
- Se calculan y comparan las cotas de rendimiento y costo (RNF-001/RNF-009).
- ``socrata_success_rate`` se mide sobre las llamadas T5 observables sin
  inventar 100% cuando no hay ninguna.
- El veredicto de puerta produce, por métrica, umbral esperado, valor
  observado y PASS/FAIL con razones bloqueantes; el smoke conserva su puerta
  específica, distinta del umbral completo de golden-v2.

Este módulo NO persiste contenido textual sensible: las estructuras que expone
para almacenar en ``eval_case_results.metrics`` solo contienen conteos,
booleanos y códigos de fallo enumerados.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from app.quality.claims import (
    ClaimRejected,
    ClaimSpec,
    EvidenceContext,
    build_claims,
    find_figures,
)
from app.tools.soql_parser import SoqlGuardError, extract_column_field_names
from eval.metrics import _collect_orphan_figures

# --- Umbrales normativos (NO se modifican aquí; se leen de pruebas.md §4.2) ---
# Estos valores son copias de los umbrales normativos existentes para producir
# el veredicto mecánico. La fuente de verdad sigue siendo pruebas.md/plan.md;
# cambiar un umbral es una decisión normativa fuera del alcance de T-617B0.
SUCCESS_RATE_THRESHOLD = 0.80  # RNF-002, positivos
NEGATIVE_SUCCESS_THRESHOLD = 1.0  # negativos 100% (pruebas.md §4.4)
RECALL_AT_10_THRESHOLD = 0.85  # RNF-004
LATENCY_SIMPLE_P95_MS = 20_000  # RNF-001
LATENCY_MULTISTEP_P95_MS = 75_000  # RNF-001
AVG_COST_USD_THRESHOLD = Decimal("0.05")  # RNF-009

# Cardinalidad exacta de una suite golden completa (pruebas.md §4.2/§4.4). La
# puerta `full` representa la ejecución COMPLETA de la suite: exactamente 50
# resultados, 40 positivos, 10 negativos y 50 case_ids únicos. Una muestra
# parcial —aunque todas sus métricas observadas sean perfectas— NUNCA puede
# certificarse como puerta completa. No son umbrales normativos de calidad:
# describen la composición fija de la suite y no relajan RNF-###.
FULL_GATE_TOTAL = 50
FULL_GATE_POSITIVES = 40
FULL_GATE_NEGATIVES = 10

# Positivos "sólidos" del smoke dirigido (pruebas.md §4.4). Ninguno puede
# retroceder en la puerta de smoke.
SMOKE_SOLID_POSITIVE_IDS: frozenset[str] = frozenset(
    {
        "pilot-002-seguridad-homicidios",
        "pilot-003-salud-vigilancia",
        "pilot-005-empleo-publico",
        "pilot-013-app-dnp",
    }
)

# Negativos canónicos del smoke dirigido (pruebas.md §4.4). Deben abstenerse
# al 100%.
SMOKE_NEGATIVE_IDS: frozenset[str] = frozenset(
    {
        "pilot-045-negativo-dato-personal",
        "pilot-046-negativo-tiempo-real",
    }
)

# Patrones diferenciados del smoke dirigido (pruebas.md §4.4). Completan, junto
# con los sólidos y los negativos, los 10 casos canónicos.
SMOKE_DIFFERENTIATED_IDS: frozenset[str] = frozenset(
    {
        "pilot-012-control-fiscal",
        "pilot-021-sensibilizacion-valle",
        "pilot-022-red-vial",
        "pilot-038-precipitacion",
    }
)

# Los 10 case_ids canónicos que el smoke dirigido DEBE ejecutar, ni más ni
# menos (pruebas.md §4.4). Faltar o añadir casos invalida la puerta de smoke
# antes de emitir veredicto.
SMOKE_CANONICAL_IDS: frozenset[str] = (
    SMOKE_SOLID_POSITIVE_IDS | SMOKE_DIFFERENTIATED_IDS | SMOKE_NEGATIVE_IDS
)

_SOCRATA_TRANSPORT_FAILURE_CODES = frozenset({"SOCRATA_TIMEOUT", "SOCRATA_ERROR"})

# Regla de clasificación simple/multipaso (documentada y probada). Un caso es
# "simple" solo cuando reproduce EXACTAMENTE "1 dataset, 1 SoQL, sin perfilado
# extenso" (pruebas.md §4.2, RNF-001):
#   - exactamente una evidencia aceptada (1 dataset),
#   - exactamente una ejecución de SoQL (`query_count` == 1),
#   - ninguna ronda de exploración de valores (`exploration_count` == 0).
# Cualquier otra corrida es "multipaso". En particular, una corrida con cero
# consultas o cero evidencias (abstención, fallo o caso no aplicable) NUNCA es
# "simple": cae en "multipaso" y, por tanto, se rige por la cota de latencia
# multipaso (más holgada), evitando contaminar el p95 simple con corridas que
# no son una consulta directa 1×1. Las corridas sin latencia observable no
# entran en ninguna muestra p95 (se filtran en `aggregate_metrics`). La regla
# usa exclusivamente señales estructuradas ya presentes en los diagnósticos por
# etapa.
SIMPLE_EVIDENCE_COUNT = 1
SIMPLE_QUERY_COUNT = 1
SIMPLE_MAX_EXPLORATIONS = 0


# --- Integridad cuantitativa de claims (RF-208/RNF-003) ----------------------


@dataclass(frozen=True)
class ClaimsIntegrityAssessment:
    """Resultado determinista de RF-208/RNF-003 sin contenido sensible.

    Solo expone conteos, fracciones, booleanos y códigos de fallo enumerados;
    nunca valores mostrados, narrativa ni filas fuente.
    """

    applicable: bool
    claim_count: int
    reproducible_claim_count: int
    total_figure_count: int
    orphan_figure_count: int
    claims_coverage: float | None
    claims_reproducible: float | None
    integrity_ok: bool
    failure_codes: tuple[str, ...] = ()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "claims-integrity-snapshot-v1",
            "applicable": self.applicable,
            "claim_count": self.claim_count,
            "reproducible_claim_count": self.reproducible_claim_count,
            "total_figure_count": self.total_figure_count,
            "orphan_figure_count": self.orphan_figure_count,
            "claims_coverage": self.claims_coverage,
            "claims_reproducible": self.claims_reproducible,
            "integrity_ok": self.integrity_ok,
            "failure_codes": list(self.failure_codes),
        }


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (DecimalException, InvalidOperation, ValueError, AttributeError):
        return None


def _resolve_execution_columns(
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, Any], ...],
    soql_query: str,
) -> tuple[tuple[str, ...], dict[str, str]] | str:
    """Resuelve las columnas de ejecución (claves reales en ``rows``) para los
    nombres públicos persistidos de un claim (RF-212, T-617C-R2).

    Camino directo (compatibilidad): si los nombres públicos ya son claves de
    ``rows`` -- claims persistidos antes de T-617C-R1, o dobles/fixtures que
    ya usan el mismo nombre como alias de ejecución -- se usan tal cual, sin
    tocar el SoQL ni construir ningún mapeo.

    Camino nuevo (T-617C-R1 en adelante): si no, se reconstruye el alias de
    ejecución real parseando ``soql_query`` con el parser SoQL vigente
    (``extract_column_field_names``, sin regex improvisada) -- el mismo
    mecanismo que ya usa ``persistence._reverify_quantitative_synthesis_fact``
    en la ruta productiva. Una columna pública sin alias correspondiente, o
    con más de un alias distinto apuntándole, falla de forma determinista en
    vez de adivinar o tomar el último silenciosamente.

    Devuelve ``(execution_columns, column_field_names)`` o un código de fallo
    (``str``) listo para ``failure_codes``.
    """

    row_keys: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            row_keys.update(row.keys())

    if set(columns) <= row_keys:
        return tuple(columns), {}

    try:
        alias_to_field = extract_column_field_names(soql_query)
    except SoqlGuardError:
        return "soql_unparseable"
    except (TypeError, ValueError):
        return "soql_unparseable"

    field_to_aliases: dict[str, list[str]] = {}
    for alias, field in alias_to_field.items():
        field_to_aliases.setdefault(field, []).append(alias)

    execution_columns: list[str] = []
    column_field_names: dict[str, str] = {}
    for name in columns:
        aliases = field_to_aliases.get(name, [])
        if not aliases:
            return "column_unresolvable"
        if len(set(aliases)) > 1:
            return "column_mapping_ambiguous"
        alias = aliases[0]
        execution_columns.append(alias)
        column_field_names[alias] = name

    return tuple(execution_columns), column_field_names


def _reproduce_one_claim(
    claim: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Reejecuta un claim público desde su evidencia. Devuelve ``None`` si
    reproduce todo (evidencia, filas, operandos, fórmula, ``raw_value``,
    ``display_value`` y ``source_hash``) o un código de fallo si algo no calza.
    """

    evidence_id = str(claim.get("evidence_id"))
    if not claim.get("evidence_id") or evidence_id not in evidence_by_id:
        return "evidence_missing"  # (2) evidence_id no existe
    evidence = evidence_by_id[evidence_id]
    rows = evidence.get("rows")
    if not isinstance(rows, list):
        return "evidence_rows_missing"
    indexes = claim.get("source_row_indexes")
    if not isinstance(indexes, (list, tuple)) or not indexes:
        return "row_reference_invalid"
    for idx in indexes:  # (3) filas referenciadas existen
        if not isinstance(idx, int) or idx < 0 or idx >= len(rows):
            return "row_out_of_range"
    columns = claim.get("columns")
    if not isinstance(columns, (list, tuple)) or not columns:
        return "columns_invalid"

    resolved = _resolve_execution_columns(
        tuple(str(c) for c in columns),
        tuple(rows),
        str(evidence.get("soql_query") or ""),
    )
    if isinstance(resolved, str):
        return resolved
    execution_columns, column_field_names = resolved

    spec = ClaimSpec(
        claim_type=str(claim.get("claim_type")),
        description="",
        source_row_indexes=tuple(int(i) for i in indexes),
        columns=execution_columns,
        column_field_names=column_field_names,
        unit=claim.get("unit"),
        rounding=claim.get("rounding"),
        formula=claim.get("formula"),
    )
    try:
        result = build_claims(  # (4) reejecuta la fórmula DSL
            EvidenceContext(
                dataset_id=str(evidence.get("dataset_id")),
                canonical_soql=str(evidence.get("soql_query") or ""),
                rows=tuple(rows),
            ),
            (spec,),
        )
    except (ClaimRejected, TypeError, ValueError, KeyError, IndexError):
        return "not_reproducible"
    if not result.claims:
        return "not_reproducible"  # operandos o columnas inexistentes
    built = result.claims[0]

    expected_raw = _to_decimal(claim.get("raw_value"))
    if expected_raw is None or built.raw_value != expected_raw:
        return "raw_value_mismatch"  # (5) resultado != raw_value
    if built.display_value != claim.get("display_value"):
        return "display_value_mismatch"  # (6)/(7) redondeo/presentación
    if built.source_hash != claim.get("source_hash"):
        return "source_hash_mismatch"
    return None


def evaluate_claims_integrity(final_answer: Mapping[str, Any]) -> ClaimsIntegrityAssessment:
    """Certifica la integridad cuantitativa completa de RF-208/RNF-003.

    No usa ``expected_facts``: reejecuta cada claim desde la evidencia
    persistida y detecta cifras huérfanas con el mismo detector normativo del
    runtime.
    """

    claims = [item for item in (final_answer.get("claims") or []) if isinstance(item, dict)]
    evidence_list = [
        item for item in (final_answer.get("evidence") or []) if isinstance(item, dict)
    ]
    evidence_by_id = {
        str(item.get("evidence_id")): item for item in evidence_list if item.get("evidence_id")
    }

    # (1) cobertura y (8) cifras huérfanas: toda cifra del texto debe estar
    # respaldada por el display_value de un claim aceptado.
    orphan_figures = _collect_orphan_figures(dict(final_answer))
    texts = [final_answer.get("summary") or "", final_answer.get("narrative") or ""]
    for evidence in evidence_list:
        if evidence.get("narrative"):
            texts.append(str(evidence.get("narrative")))
    total_figures = sum(len(find_figures(text)) for text in texts)

    applicable = bool(claims or total_figures)
    if not applicable:
        return ClaimsIntegrityAssessment(
            applicable=False,
            claim_count=0,
            reproducible_claim_count=0,
            total_figure_count=0,
            orphan_figure_count=0,
            claims_coverage=None,
            claims_reproducible=None,
            integrity_ok=True,
        )

    failure_codes: list[str] = []
    reproducible = 0
    for claim in claims:
        code = _reproduce_one_claim(claim, evidence_by_id)
        if code is None:
            reproducible += 1
        else:
            failure_codes.append(code)

    orphan_count = len(orphan_figures)
    if orphan_count:
        failure_codes.append("orphan_figures")
    # cota defensiva: nunca más huérfanas que cifras contadas
    orphan_count = min(orphan_count, total_figures) if total_figures else orphan_count

    coverage = 1.0 if total_figures == 0 else (total_figures - orphan_count) / total_figures
    reproducible_ratio = 1.0 if not claims else reproducible / len(claims)
    integrity_ok = coverage == 1.0 and reproducible_ratio == 1.0 and orphan_count == 0

    return ClaimsIntegrityAssessment(
        applicable=True,
        claim_count=len(claims),
        reproducible_claim_count=reproducible,
        total_figure_count=total_figures,
        orphan_figure_count=orphan_count,
        claims_coverage=coverage,
        claims_reproducible=reproducible_ratio,
        integrity_ok=integrity_ok,
        failure_codes=tuple(dict.fromkeys(failure_codes)),
    )


# --- Clasificación de complejidad (RNF-001) ----------------------------------


def classify_run_complexity(diagnostics: Mapping[str, Any]) -> str:
    """Clasifica una corrida como ``"simple"`` o ``"multistep"`` con señales
    estructuradas verificables (regla documentada arriba)."""

    evidence_count = int(diagnostics.get("evidence_count") or 0)
    query_count = int(diagnostics.get("query_count") or 0)
    exploration_count = int(diagnostics.get("exploration_count") or 0)
    if (
        evidence_count == SIMPLE_EVIDENCE_COUNT
        and query_count == SIMPLE_QUERY_COUNT
        and exploration_count <= SIMPLE_MAX_EXPLORATIONS
    ):
        return "simple"
    return "multistep"


# --- Percentiles deterministas (nearest-rank) --------------------------------


def percentile(values: Sequence[float], q: float) -> float | None:
    """Percentil por rango más cercano (nearest-rank), determinista.

    Para ``n`` valores ordenados y cuantil ``q`` en [0, 1], el rango es
    ``ceil(q * n)`` acotado a [1, n]; se devuelve el valor en esa posición
    (base 1). Elegido por ser reproducible y no interpolar entre muestras.
    """

    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return None
    rank = math.ceil(q * len(clean))
    index = min(max(rank, 1), len(clean)) - 1
    return clean[index]


# --- socrata_success_rate (RF/pruebas.md §4.2) -------------------------------


def socrata_success_rate(observations: Iterable[Any]) -> tuple[int, int] | None:
    """(éxitos, intentos) de llamadas T5 observables o ``None`` si no hay
    ninguna medible.

    Una observación cuenta como llamada T5 cuando expone el resultado crudo de
    la herramienta ``ejecutar_soql`` (dict con clave ``ok`` o ``error``). Un
    fallo de transporte Socrata es un ``error.code`` en
    ``{SOCRATA_TIMEOUT, SOCRATA_ERROR}``; los rechazos posteriores de
    elegibilidad ocurren en T6 y no descuentan aquí. No inventa 100%: si
    ninguna observación expone un resultado T5, devuelve ``None``.
    """

    attempts = 0
    successes = 0
    for observation in observations:
        output = getattr(observation, "output", None)
        if not isinstance(output, Mapping):
            continue
        has_ok = "ok" in output
        error = output.get("error")
        has_error = isinstance(error, Mapping) and "code" in error
        if not (has_ok or has_error):
            continue
        attempts += 1
        code = error.get("code") if isinstance(error, Mapping) else None
        if code in _SOCRATA_TRANSPORT_FAILURE_CODES:
            continue
        successes += 1
    if attempts == 0:
        return None
    return successes, attempts


# --- Resultado por caso y agregación -----------------------------------------


@dataclass(frozen=True)
class CaseOutcome:
    """Vista mínima por caso para agregación y veredicto (sin I/O)."""

    case_id: str
    case_type: str
    passed: bool
    fabrication: bool
    recall_hit: bool | None
    failure_stage: str | None
    failure_code: str | None
    complexity: str
    latency_ms: int | None
    cost_usd: Decimal | None
    claims_integrity: ClaimsIntegrityAssessment
    socrata_successes: int
    socrata_attempts: int
    # T-617B0-R3: transporta de forma estructurada (booleano, no texto) si la
    # corrida terminó por una falla de infraestructura/proveedor
    # (`failure_owner="infrastructure"`, eval.diagnostics). Una corrida así
    # nunca cuenta como regresión semántica en `positivos_sólidos`, pero
    # bloquea la puerta por su propia métrica de infraestructura, sin
    # excluirse de ningún denominador.
    infrastructure_failure: bool = False


@dataclass(frozen=True)
class AggregateMetrics:
    measured_total: int
    distinct_case_id_count: int
    positive_total: int
    positive_passed: int
    negative_total: int
    negative_passed: int
    success_rate: float | None
    negative_success_rate: float | None
    recall_at_10: float | None
    recall_hits: int
    recall_measured_count: int
    fabrication_count: int
    orphan_figures_count: int
    claims_coverage: float | None
    claims_reproducible: float | None
    claims_integrity_ok: bool
    latency_measured_count: int
    cost_measured_count: int
    simple_sample_count: int
    multistep_sample_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_simple_p95_ms: float | None
    latency_multistep_p95_ms: float | None
    avg_cost_usd: Decimal | None
    socrata_success_rate: float | None
    socrata_successes: int
    socrata_attempts: int
    # T-617B0-R3: cuenta y case_ids de corridas con falla de infraestructura o
    # proveedor. Nunca se excluyen de ningún otro denominador de esta
    # estructura (positivos/negativos/latencia/costo siguen incluyéndolas);
    # esto solo expone la señal para que la puerta bloquee explícitamente.
    infrastructure_failure_count: int
    infrastructure_failure_case_ids: tuple[str, ...]


def aggregate_metrics(outcomes: Sequence[CaseOutcome]) -> AggregateMetrics:
    positives = [o for o in outcomes if o.case_type == "positive"]
    negatives = [o for o in outcomes if o.case_type == "negative"]

    positive_passed = sum(o.passed for o in positives)
    negative_passed = sum(o.passed for o in negatives)
    # recall_at_10 se calcula sobre TODOS los positivos, no solo los medidos:
    # un positivo sin señal de recuperación (`recall_hit is None`) cuenta como
    # miss y jamás se excluye silenciosamente del denominador (RNF-004). Así,
    # un True + un None nunca produce 100%. `recall_measured_count` se registra
    # aparte para exponer cuántos positivos sí tuvieron medición.
    recall_hits = sum(1 for o in positives if o.recall_hit is True)
    recall_measured_count = sum(1 for o in positives if o.recall_hit is not None)

    applicable_integrity = [o for o in outcomes if o.claims_integrity.applicable]
    coverages = [
        o.claims_integrity.claims_coverage
        for o in applicable_integrity
        if o.claims_integrity.claims_coverage is not None
    ]
    reproducibles = [
        o.claims_integrity.claims_reproducible
        for o in applicable_integrity
        if o.claims_integrity.claims_reproducible is not None
    ]

    latencies = [float(o.latency_ms) for o in outcomes if o.latency_ms is not None]
    simple_latencies = [
        float(o.latency_ms)
        for o in outcomes
        if o.latency_ms is not None and o.complexity == "simple"
    ]
    multistep_latencies = [
        float(o.latency_ms)
        for o in outcomes
        if o.latency_ms is not None and o.complexity == "multistep"
    ]
    costs = [o.cost_usd for o in outcomes if o.cost_usd is not None]

    socrata_successes = sum(o.socrata_successes for o in outcomes)
    socrata_attempts = sum(o.socrata_attempts for o in outcomes)

    infra_failures = tuple(o.case_id for o in outcomes if o.infrastructure_failure)

    return AggregateMetrics(
        measured_total=len(outcomes),
        distinct_case_id_count=len({o.case_id for o in outcomes}),
        positive_total=len(positives),
        positive_passed=positive_passed,
        negative_total=len(negatives),
        negative_passed=negative_passed,
        success_rate=(positive_passed / len(positives)) if positives else None,
        negative_success_rate=(negative_passed / len(negatives)) if negatives else None,
        recall_at_10=(recall_hits / len(positives)) if positives else None,
        recall_hits=recall_hits,
        recall_measured_count=recall_measured_count,
        fabrication_count=sum(o.fabrication for o in outcomes),
        orphan_figures_count=sum(o.claims_integrity.orphan_figure_count for o in outcomes),
        claims_coverage=(sum(coverages) / len(coverages)) if coverages else None,
        claims_reproducible=(sum(reproducibles) / len(reproducibles)) if reproducibles else None,
        claims_integrity_ok=all(o.claims_integrity.integrity_ok for o in outcomes),
        latency_measured_count=len(latencies),
        cost_measured_count=len(costs),
        simple_sample_count=len(simple_latencies),
        multistep_sample_count=len(multistep_latencies),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
        latency_simple_p95_ms=percentile(simple_latencies, 0.95),
        latency_multistep_p95_ms=percentile(multistep_latencies, 0.95),
        avg_cost_usd=(sum(costs, Decimal(0)) / Decimal(len(costs))) if costs else None,
        socrata_success_rate=((socrata_successes / socrata_attempts) if socrata_attempts else None),
        socrata_successes=socrata_successes,
        socrata_attempts=socrata_attempts,
        infrastructure_failure_count=len(infra_failures),
        infrastructure_failure_case_ids=infra_failures,
    )


# --- Veredicto de puerta -----------------------------------------------------


@dataclass(frozen=True)
class GateMetric:
    name: str
    threshold: str
    observed: str
    passed: bool
    reason: str | None = None


@dataclass(frozen=True)
class GateVerdict:
    mode: str
    passed: bool
    metrics: tuple[GateMetric, ...]

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        return tuple(m.reason for m in self.metrics if not m.passed and m.reason)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def evaluate_full_gate(aggregate: AggregateMetrics) -> GateVerdict:
    """Veredicto de la puerta completa (golden-v2). El exit code NO puede
    depender solo de ``success_rate``: FALLA si incumple cualquier condición
    normativa medible con LLM real."""

    metrics: list[GateMetric] = []

    def add(name, threshold, observed, passed, reason):
        metrics.append(GateMetric(name, threshold, observed, passed, None if passed else reason))

    # Cardinalidad de suite completa (pruebas.md §4.2/§4.4): la puerta `full`
    # representa la ejecución COMPLETA de la suite. Una muestra parcial —aunque
    # todas sus métricas observadas sean perfectas— NUNCA puede certificarse
    # como puerta completa. Se exige, ANTES de cualquier umbral de calidad,
    # exactamente 50 resultados, 40 positivos, 10 negativos y 50 case_ids
    # únicos. Esta condición no relaja ningún umbral normativo: describe la
    # composición fija de la suite.
    total = aggregate.measured_total
    cardinality_parts: list[str] = []
    if total != FULL_GATE_TOTAL:
        cardinality_parts.append(f"total={total} (esperado {FULL_GATE_TOTAL})")
    if aggregate.positive_total != FULL_GATE_POSITIVES:
        cardinality_parts.append(
            f"positivos={aggregate.positive_total} (esperado {FULL_GATE_POSITIVES})"
        )
    if aggregate.negative_total != FULL_GATE_NEGATIVES:
        cardinality_parts.append(
            f"negativos={aggregate.negative_total} (esperado {FULL_GATE_NEGATIVES})"
        )
    if aggregate.distinct_case_id_count != total:
        cardinality_parts.append(
            f"case_ids únicos={aggregate.distinct_case_id_count} (esperado {total})"
        )
    add(
        "cardinalidad_suite",
        f"{FULL_GATE_TOTAL} resultados = {FULL_GATE_POSITIVES} positivos "
        f"+ {FULL_GATE_NEGATIVES} negativos, {FULL_GATE_TOTAL} case_ids únicos",
        f"{total} resultados = {aggregate.positive_total} positivos "
        f"+ {aggregate.negative_total} negativos, "
        f"{aggregate.distinct_case_id_count} case_ids únicos",
        not cardinality_parts,
        "selección incompatible con la puerta completa: " + "; ".join(cardinality_parts)
        if cardinality_parts
        else None,
    )

    # T-617B0-R3: cero corridas no evaluables por infraestructura/proveedor.
    # Se exige ANTES de cualquier umbral de calidad, igual que la
    # cardinalidad: una corrida con infraestructura incompleta NUNCA puede
    # certificar la puerta completa, aunque el resto de métricas observadas
    # sea perfecto.
    infra_failed = list(aggregate.infrastructure_failure_case_ids)
    add(
        "infraestructura",
        "0 corridas no evaluables por infraestructura/proveedor",
        f"{len(infra_failed)} corridas no evaluables"
        + (f" ({', '.join(infra_failed)})" if infra_failed else ""),
        not infra_failed,
        "falla de infraestructura/proveedor bloquea la puerta: " + ", ".join(infra_failed)
        if infra_failed
        else None,
    )

    # RNF-002: positivos >= 80%
    sr = aggregate.success_rate
    add(
        "success_rate (positivos)",
        f">= {SUCCESS_RATE_THRESHOLD:.0%}",
        _fmt(sr),
        sr is not None and sr >= SUCCESS_RATE_THRESHOLD,
        "success_rate de positivos por debajo del 80% (RNF-002)",
    )
    # Negativos 100% (pruebas.md §4.4)
    nsr = aggregate.negative_success_rate
    add(
        "negative_success_rate",
        "== 100%",
        _fmt(nsr),
        nsr is not None and nsr >= NEGATIVE_SUCCESS_THRESHOLD,
        "algún caso negativo no se abstuvo (negativos != 100%)",
    )
    # RNF-005: fabricaciones 0
    add(
        "fabrication_count",
        "== 0",
        _fmt(aggregate.fabrication_count),
        aggregate.fabrication_count == 0,
        "hubo fabricaciones en casos negativos (RNF-005)",
    )
    # RNF-003: cifras huérfanas 0
    add(
        "orphan_figures_count",
        "== 0",
        _fmt(aggregate.orphan_figures_count),
        aggregate.orphan_figures_count == 0,
        "hay cifras huérfanas sin claim que las respalde (RNF-003)",
    )
    # RF-208/RNF-003: cobertura y reproducibilidad completas
    add(
        "claims_integrity",
        "cobertura=100% y reproducibles=100%",
        f"cobertura={_fmt(aggregate.claims_coverage)} "
        f"reproducibles={_fmt(aggregate.claims_reproducible)}",
        aggregate.claims_integrity_ok,
        "integridad de claims incompleta (cobertura/reproducibilidad < 100%, RF-208/RNF-003)",
    )
    # RNF-004: recall@10 >= 85%
    recall = aggregate.recall_at_10
    add(
        "recall_at_10",
        f">= {RECALL_AT_10_THRESHOLD:.0%}",
        _fmt(recall),
        recall is not None and recall >= RECALL_AT_10_THRESHOLD,
        "recall@10 por debajo del 85% (RNF-004)",
    )
    # Completitud de medición (RNF-001/RNF-009): la puerta completa NO puede
    # certificarse con latencia o costo sin medir. Cualquier caso sin latencia
    # o sin costo observado produce FAIL con conteo medido/esperado explícito.
    add(
        "latencia_medida",
        f"medida en {total}/{total} casos",
        f"{aggregate.latency_measured_count}/{total}",
        total > 0 and aggregate.latency_measured_count == total,
        "medición de latencia incompleta: hay casos sin latencia observada (RNF-001)",
    )
    add(
        "costo_medido",
        f"medido en {total}/{total} casos",
        f"{aggregate.cost_measured_count}/{total}",
        total > 0 and aggregate.cost_measured_count == total,
        "medición de costo incompleta: hay casos sin costo observado (RNF-009)",
    )
    # RNF-001: latencia p95 simple/multipaso. Se exige muestra válida (no vacía)
    # en AMBAS particiones; un p95 None (sin muestra) NUNCA aprueba.
    ls = aggregate.latency_simple_p95_ms
    add(
        "latency_simple_p95_ms",
        f"<= {LATENCY_SIMPLE_P95_MS} con muestra válida",
        f"{_fmt(ls)} (n={aggregate.simple_sample_count})",
        ls is not None and ls <= LATENCY_SIMPLE_P95_MS,
        "sin muestra simple medible o p95 de latencia simple supera 20 s (RNF-001)",
    )
    lm = aggregate.latency_multistep_p95_ms
    add(
        "latency_multistep_p95_ms",
        f"<= {LATENCY_MULTISTEP_P95_MS} con muestra válida",
        f"{_fmt(lm)} (n={aggregate.multistep_sample_count})",
        lm is not None and lm <= LATENCY_MULTISTEP_P95_MS,
        "sin muestra multipaso medible o p95 de latencia multipaso supera 75 s (RNF-001)",
    )
    # RNF-009: costo promedio. Un costo None (sin medición) NUNCA aprueba.
    cost = aggregate.avg_cost_usd
    add(
        "avg_cost_usd",
        f"<= {AVG_COST_USD_THRESHOLD}",
        _fmt(cost),
        cost is not None and cost <= AVG_COST_USD_THRESHOLD,
        "costo promedio ausente o supera 0,05 USD por corrida (RNF-009)",
    )

    passed = all(m.passed for m in metrics)
    return GateVerdict(mode="full", passed=passed, metrics=tuple(metrics))


def evaluate_smoke_gate(
    outcomes: Sequence[CaseOutcome],
    *,
    solid_positive_ids: frozenset[str] = SMOKE_SOLID_POSITIVE_IDS,
    canonical_ids: frozenset[str] = SMOKE_CANONICAL_IDS,
) -> GateVerdict:
    """Puerta específica del smoke dirigido (pruebas.md §4.4), distinta del
    umbral completo de golden-v2: se ejecutan EXACTAMENTE los 10 case_ids
    canónicos (4 sólidos, 4 patrones diferenciados y 2 negativos), los
    negativos se abstienen al 100%, ningún positivo sólido retrocede y todo
    fallo tiene etapa y código."""

    metrics: list[GateMetric] = []

    # Cobertura canónica: faltar, añadir o REPETIR casos invalida el smoke ANTES
    # de cualquier otro veredicto (pruebas.md §4.4). El smoke ejecuta EXACTAMENTE
    # los 10 case_ids canónicos, una sola vez cada uno; ejecutar solo un
    # subconjunto (p. ej. dos negativos) o repetir un caso —lo que infla el
    # número de resultados sin cambiar el conjunto de IDs únicos— nunca puede
    # aprobar.
    id_counts = Counter(o.case_id for o in outcomes)
    present_ids = set(id_counts)
    missing = sorted(canonical_ids - present_ids)
    extra = sorted(present_ids - canonical_ids)
    duplicates = sorted(cid for cid, count in id_counts.items() if count > 1)
    coverage_reason_parts: list[str] = []
    if missing:
        coverage_reason_parts.append(f"faltan: {', '.join(missing)}")
    if extra:
        coverage_reason_parts.append(f"sobran: {', '.join(extra)}")
    if duplicates:
        coverage_reason_parts.append(f"duplicados: {', '.join(duplicates)}")
    metrics.append(
        GateMetric(
            "cobertura_canónica",
            f"exactamente {len(canonical_ids)} canónicos, uno por caso",
            f"{len(present_ids & canonical_ids)}/{len(canonical_ids)} canónicos, "
            f"{len(outcomes)} resultados"
            + (f", {len(extra)} no canónicos" if extra else "")
            + (f", {len(duplicates)} duplicados" if duplicates else ""),
            not missing and not extra and not duplicates,
            None if not coverage_reason_parts else "; ".join(coverage_reason_parts),
        )
    )

    negatives = [o for o in outcomes if o.case_type == "negative"]
    negatives_passed = sum(o.passed for o in negatives)
    metrics.append(
        GateMetric(
            "negativos",
            f"{len(negatives)}/{len(negatives)}",
            f"{negatives_passed}/{len(negatives)}",
            len(negatives) > 0 and negatives_passed == len(negatives),
            None
            if negatives and negatives_passed == len(negatives)
            else "algún negativo del smoke no se abstuvo",
        )
    )

    # T-617B0-R3: un sólido que falló por infraestructura/proveedor (p. ej.
    # 504 del LLM en `build_plan`, `failure_owner="infrastructure"`) NO es una
    # regresión semántica del agente: se excluye de esta lista para no
    # atribuirle al agente un fallo que no le pertenece. Sigue bloqueando la
    # puerta, pero por la métrica "infraestructura" de abajo.
    solid = [o for o in outcomes if o.case_id in solid_positive_ids]
    regressed = [o.case_id for o in solid if not o.passed and not o.infrastructure_failure]
    metrics.append(
        GateMetric(
            "positivos_sólidos",
            "0 retrocesos",
            f"{len(regressed)} retrocesos",
            not regressed,
            None if not regressed else f"positivos sólidos que retroceden: {', '.join(regressed)}",
        )
    )

    # T-617B0-R3: cero corridas no evaluables por infraestructura/proveedor,
    # canónicas o no. Un caso así nunca puede producir PASS en el smoke,
    # aunque el resto de la puerta esté verde.
    infra_failed = [o.case_id for o in outcomes if o.infrastructure_failure]
    metrics.append(
        GateMetric(
            "infraestructura",
            "0 corridas no evaluables por infraestructura/proveedor",
            f"{len(infra_failed)} corridas no evaluables"
            + (f" ({', '.join(infra_failed)})" if infra_failed else ""),
            not infra_failed,
            None
            if not infra_failed
            else "falla de infraestructura/proveedor bloquea la puerta: " + ", ".join(infra_failed),
        )
    )

    unclassified = [
        o.case_id for o in outcomes if not o.passed and not (o.failure_stage and o.failure_code)
    ]
    metrics.append(
        GateMetric(
            "fallos_clasificados",
            "todo fallo con etapa+código",
            f"{len(unclassified)} sin clasificar",
            not unclassified,
            None if not unclassified else f"fallos sin etapa/código: {', '.join(unclassified)}",
        )
    )

    # T-617C-R2: RF-208/RNF-003 -- toda cifra presentada debe conservar
    # cobertura de claims=100%, reproducibilidad=100% y cero cifras huérfanas
    # en TODO caso donde la integridad de claims sea aplicable (tenga claims o
    # cifras en el texto). No evalúa perfección de respuesta ni coincidencia
    # con expected_facts: solo trazabilidad y reproducibilidad ya calculadas
    # por evaluate_claims_integrity. Antes de esta métrica, un fallo de
    # reproducibilidad (p. ej. el defecto de _reproduce_one_claim que motivó
    # esta ronda) podía dejar pasar el smoke sin que ninguna métrica lo
    # bloqueara.
    broken_integrity = [
        o.case_id
        for o in outcomes
        if o.claims_integrity.applicable and not o.claims_integrity.integrity_ok
    ]
    metrics.append(
        GateMetric(
            "integridad_claims",
            "cobertura=100%, reproducibles=100%, huérfanas=0 en todo caso aplicable",
            f"{len(broken_integrity)} casos con integridad rota"
            + (f" ({', '.join(broken_integrity)})" if broken_integrity else ""),
            not broken_integrity,
            None
            if not broken_integrity
            else "integridad de claims rota (RF-208/RNF-003): " + ", ".join(broken_integrity),
        )
    )

    passed = all(m.passed for m in metrics)
    return GateVerdict(mode="smoke", passed=passed, metrics=tuple(metrics))


def evaluate_directed_gate() -> GateVerdict:
    """Veredicto trivial para el modo ``directed`` (T-617B-C2, validación
    dirigida de casos concretos): no certifica ninguna condición normativa de
    ``full`` ni de ``smoke``. ``metrics=()`` deja explícito que no hay
    umbrales evaluados; ``passed=True`` es un valor neutro para no bloquear
    el exit code de un modo que, por diseño, no tiene condición de fallo —
    el reporte (``_gate_summary_lines`` en ``eval/run.py``) debe dejar
    explícito para el lector que esto no es un veredicto PASS/FAIL de
    puerta."""

    return GateVerdict(mode="directed", passed=True, metrics=())


# --- Preflight de selección (fail-fast antes de gastar cuota) -----------------


def validate_gate_selection(cases: Iterable[Any], gate_mode: str) -> None:
    """Valida que la selección de casos sea compatible con la puerta ANTES de
    crear el engine, abrir conexiones o invocar cualquier proveedor externo.

    Función PURA (sin I/O): recibe un iterable de casos con atributos
    ``case_id`` y ``case_type`` y lanza ``RuntimeError`` con un mensaje claro y
    sin datos sensibles si la selección no puede certificar la puerta pedida.
    No aprueba ni ejecuta nada: solo evita gastar cuota cuando ``--limit`` o
    ``--case-id`` dejan una selección incompatible.

    - ``full``: exactamente 50 casos, 40 positivos, 10 negativos, sin case_ids
      duplicados (la ejecución completa de la suite golden, pruebas.md
      §4.2/§4.4).
    - ``smoke``: exactamente los 10 ``SMOKE_CANONICAL_IDS``, una sola vez cada
      uno; sin faltantes, extras ni duplicados (pruebas.md §4.4).
    - ``directed``: cualquier subconjunto explícito no vacío de la suite, sin
      case_ids duplicados. No certifica ninguna puerta normativa (ni ``full``
      ni ``smoke``): sólo valida que la selección sea ejecutable, para
      validaciones dirigidas de casos concretos (p. ej. tras un incremento de
      código, T-617B-C2) sin implicar un veredicto PASS/FAIL de la suite.
    - Cualquier otro ``gate_mode`` se rechaza explícitamente.
    """

    selected = list(cases)
    case_ids = [case.case_id for case in selected]
    id_counts = Counter(case_ids)
    duplicates = sorted(cid for cid, count in id_counts.items() if count > 1)

    if gate_mode == "directed":
        problems: list[str] = []
        if not case_ids:
            problems.append("selección vacía: modo directed exige al menos un case_id")
        if duplicates:
            problems.append(f"case_ids duplicados: {', '.join(duplicates)}")
        if problems:
            raise RuntimeError(
                "selección incompatible con el modo directed: " + "; ".join(problems)
            )
        return

    if gate_mode == "full":
        total = len(case_ids)
        positives = sum(1 for case in selected if getattr(case, "case_type", None) == "positive")
        negatives = sum(1 for case in selected if getattr(case, "case_type", None) == "negative")
        problems: list[str] = []
        if total != FULL_GATE_TOTAL:
            problems.append(f"total={total} (esperado {FULL_GATE_TOTAL})")
        if positives != FULL_GATE_POSITIVES:
            problems.append(f"positivos={positives} (esperado {FULL_GATE_POSITIVES})")
        if negatives != FULL_GATE_NEGATIVES:
            problems.append(f"negativos={negatives} (esperado {FULL_GATE_NEGATIVES})")
        if duplicates:
            problems.append(f"case_ids duplicados: {', '.join(duplicates)}")
        if problems:
            raise RuntimeError("selección incompatible con la puerta full: " + "; ".join(problems))
        return

    if gate_mode == "smoke":
        present_ids = set(id_counts)
        missing = sorted(SMOKE_CANONICAL_IDS - present_ids)
        extra = sorted(present_ids - SMOKE_CANONICAL_IDS)
        problems = []
        if missing:
            problems.append(f"faltan: {', '.join(missing)}")
        if extra:
            problems.append(f"sobran: {', '.join(extra)}")
        if duplicates:
            problems.append(f"duplicados: {', '.join(duplicates)}")
        if problems:
            raise RuntimeError("selección incompatible con la puerta smoke: " + "; ".join(problems))
        return

    raise RuntimeError(
        f"gate_mode desconocido: {gate_mode!r} (esperado 'full', 'smoke' o 'directed')"
    )
