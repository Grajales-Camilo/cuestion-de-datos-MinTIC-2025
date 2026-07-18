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

_SOCRATA_TRANSPORT_FAILURE_CODES = frozenset({"SOCRATA_TIMEOUT", "SOCRATA_ERROR"})

# Regla de clasificación simple/multipaso (documentada y probada). Un caso es
# "simple" cuando reproduce literalmente "1 dataset, 1 SoQL, sin perfilado
# extenso" (pruebas.md §4.2, RNF-001):
#   - a lo sumo una evidencia aceptada (1 dataset),
#   - a lo sumo una ejecución de SoQL (`query_count` <= 1),
#   - ninguna ronda de exploración de valores (`exploration_count` == 0).
# Cualquier otra corrida es "multipaso". La regla usa exclusivamente señales
# estructuradas de la corrida ya presentes en los diagnósticos por etapa.
SIMPLE_MAX_EVIDENCE = 1
SIMPLE_MAX_QUERIES = 1
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

    spec = ClaimSpec(
        claim_type=str(claim.get("claim_type")),
        description="",
        source_row_indexes=tuple(int(i) for i in indexes),
        columns=tuple(str(c) for c in columns),
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
        evidence_count <= SIMPLE_MAX_EVIDENCE
        and query_count <= SIMPLE_MAX_QUERIES
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


@dataclass(frozen=True)
class AggregateMetrics:
    positive_total: int
    positive_passed: int
    negative_total: int
    negative_passed: int
    success_rate: float | None
    negative_success_rate: float | None
    recall_at_10: float | None
    fabrication_count: int
    orphan_figures_count: int
    claims_coverage: float | None
    claims_reproducible: float | None
    claims_integrity_ok: bool
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_simple_p95_ms: float | None
    latency_multistep_p95_ms: float | None
    avg_cost_usd: Decimal | None
    socrata_success_rate: float | None
    socrata_successes: int
    socrata_attempts: int


def aggregate_metrics(outcomes: Sequence[CaseOutcome]) -> AggregateMetrics:
    positives = [o for o in outcomes if o.case_type == "positive"]
    negatives = [o for o in outcomes if o.case_type == "negative"]

    positive_passed = sum(o.passed for o in positives)
    negative_passed = sum(o.passed for o in negatives)
    # recall_at_10 solo aplica a positivos con señal de recuperación medida
    recall_pool = [o for o in positives if o.recall_hit is not None]
    recall_hits = sum(bool(o.recall_hit) for o in recall_pool)

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

    return AggregateMetrics(
        positive_total=len(positives),
        positive_passed=positive_passed,
        negative_total=len(negatives),
        negative_passed=negative_passed,
        success_rate=(positive_passed / len(positives)) if positives else None,
        negative_success_rate=(negative_passed / len(negatives)) if negatives else None,
        recall_at_10=(recall_hits / len(recall_pool)) if recall_pool else None,
        fabrication_count=sum(o.fabrication for o in outcomes),
        orphan_figures_count=sum(o.claims_integrity.orphan_figure_count for o in outcomes),
        claims_coverage=(sum(coverages) / len(coverages)) if coverages else None,
        claims_reproducible=(sum(reproducibles) / len(reproducibles)) if reproducibles else None,
        claims_integrity_ok=all(o.claims_integrity.integrity_ok for o in outcomes),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
        latency_simple_p95_ms=percentile(simple_latencies, 0.95),
        latency_multistep_p95_ms=percentile(multistep_latencies, 0.95),
        avg_cost_usd=(sum(costs, Decimal(0)) / Decimal(len(costs))) if costs else None,
        socrata_success_rate=((socrata_successes / socrata_attempts) if socrata_attempts else None),
        socrata_successes=socrata_successes,
        socrata_attempts=socrata_attempts,
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
    # RNF-001: latencia p95 simple/multipaso
    ls = aggregate.latency_simple_p95_ms
    add(
        "latency_simple_p95_ms",
        f"<= {LATENCY_SIMPLE_P95_MS}",
        _fmt(ls),
        ls is None or ls <= LATENCY_SIMPLE_P95_MS,
        "p95 de latencia simple supera 20 s (RNF-001)",
    )
    lm = aggregate.latency_multistep_p95_ms
    add(
        "latency_multistep_p95_ms",
        f"<= {LATENCY_MULTISTEP_P95_MS}",
        _fmt(lm),
        lm is None or lm <= LATENCY_MULTISTEP_P95_MS,
        "p95 de latencia multipaso supera 75 s (RNF-001)",
    )
    # RNF-009: costo promedio
    cost = aggregate.avg_cost_usd
    add(
        "avg_cost_usd",
        f"<= {AVG_COST_USD_THRESHOLD}",
        _fmt(cost),
        cost is None or cost <= AVG_COST_USD_THRESHOLD,
        "costo promedio por corrida supera 0,05 USD (RNF-009)",
    )

    passed = all(m.passed for m in metrics)
    return GateVerdict(mode="full", passed=passed, metrics=tuple(metrics))


def evaluate_smoke_gate(
    outcomes: Sequence[CaseOutcome],
    *,
    solid_positive_ids: frozenset[str] = SMOKE_SOLID_POSITIVE_IDS,
) -> GateVerdict:
    """Puerta específica del smoke dirigido (pruebas.md §4.4), distinta del
    umbral completo de golden-v2: negativos 100%, ningún positivo sólido
    retrocede y todo fallo tiene etapa y código."""

    metrics: list[GateMetric] = []
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

    solid = [o for o in outcomes if o.case_id in solid_positive_ids]
    regressed = [o.case_id for o in solid if not o.passed]
    metrics.append(
        GateMetric(
            "positivos_sólidos",
            "0 retrocesos",
            f"{len(regressed)} retrocesos",
            not regressed,
            None if not regressed else f"positivos sólidos que retroceden: {', '.join(regressed)}",
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

    passed = all(m.passed for m in metrics)
    return GateVerdict(mode="smoke", passed=passed, metrics=tuple(metrics))
