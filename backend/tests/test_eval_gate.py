"""Pruebas deterministas de la instrumentación de puerta (T-617B0).

No ejecutan LLM, red ni base de datos: operan sobre estructuras materializadas.
Demuestran los huecos cerrados y sus bordes.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.quality.claims import ClaimSpec, EvidenceContext, build_claims
from eval.gate import (
    AVG_COST_USD_THRESHOLD,
    SMOKE_CANONICAL_IDS,
    CaseOutcome,
    ClaimsIntegrityAssessment,
    aggregate_metrics,
    classify_run_complexity,
    evaluate_claims_integrity,
    evaluate_full_gate,
    evaluate_smoke_gate,
    percentile,
    socrata_success_rate,
    validate_gate_selection,
)
from eval.run import _case_result_model, _gate_summary_lines, apply_aggregate_metrics

# --- Utilidades de construcción ----------------------------------------------


def _valid_final(*, summary: str | None = None) -> dict:
    """final_answer con un claim cuantitativo reproducible de punta a punta."""

    rows = ({"total": "100"},)
    evidence_id = str(uuid.uuid4())
    spec = ClaimSpec(
        claim_type="direct",
        description="Total de registros",
        source_row_indexes=(0,),
        columns=("total",),
    )
    built = build_claims(
        EvidenceContext(dataset_id="abcd-1234", canonical_soql="SELECT total", rows=rows),
        (spec,),
    ).claims[0]
    claim = {
        "claim_id": str(uuid.uuid4()),
        "claim": f"Total de registros: {built.display_value}",
        "claim_type": "direct",
        "evidence_id": evidence_id,
        "dataset_id": "abcd-1234",
        "source_row_indexes": list(built.source_row_indexes),
        "columns": list(built.columns_used),
        "formula": built.formula,
        "raw_value": int(built.raw_value),
        "display_value": built.display_value,
        "unit": built.unit,
        "rounding": built.rounding,
        "source_hash": built.source_hash,
    }
    evidence = {
        "evidence_id": evidence_id,
        "dataset_id": "abcd-1234",
        "soql_query": "SELECT total",
        "rows": list(rows),
        "narrative": None,
    }
    return {
        "status": "completed",
        "claims": [claim],
        "evidence": [evidence],
        "summary": summary if summary is not None else f"El total es {built.display_value}.",
    }


def _trivial_integrity() -> ClaimsIntegrityAssessment:
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


def _outcome(
    case_id: str,
    case_type: str,
    passed: bool,
    *,
    fabrication: bool = False,
    recall_hit: bool | None = None,
    failure_stage: str | None = None,
    failure_code: str | None = None,
    complexity: str = "simple",
    latency_ms: int | None = 1000,
    cost_usd: Decimal | None = Decimal("0.01"),
    integrity: ClaimsIntegrityAssessment | None = None,
    socrata: tuple[int, int] = (1, 1),
) -> CaseOutcome:
    if not passed and failure_stage is None:
        failure_stage, failure_code = "acceptance", "intent_mismatch"
    if recall_hit is None and case_type == "positive":
        recall_hit = passed
    return CaseOutcome(
        case_id=case_id,
        case_type=case_type,
        passed=passed,
        fabrication=fabrication,
        recall_hit=recall_hit,
        failure_stage=failure_stage,
        failure_code=failure_code,
        complexity=complexity,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        claims_integrity=integrity or _trivial_integrity(),
        socrata_successes=socrata[0],
        socrata_attempts=socrata[1],
    )


def _suite(positives_passed: int, negatives_passed: int, *, positives=40, negatives=10):
    outcomes = []
    # Complejidad partida por paridad: ambas particiones (simple/multipaso)
    # quedan pobladas para que la puerta completa disponga de muestra p95 válida
    # en las dos, y toda corrida tiene latencia y costo medidos.
    for i in range(positives):
        complexity = "simple" if i % 2 == 0 else "multistep"
        outcomes.append(
            _outcome(f"pos-{i}", "positive", i < positives_passed, complexity=complexity)
        )
    for i in range(negatives):
        passed = i < negatives_passed
        outcomes.append(_outcome(f"neg-{i}", "negative", passed, fabrication=not passed))
    return outcomes


def _positive_recall_none(case_id: str) -> CaseOutcome:
    """Positivo aprobado pero SIN señal de recuperación medida (recall_hit
    None). Se construye directo porque `_outcome` enmascara None → passed para
    positivos; aquí queremos el None genuino."""

    return CaseOutcome(
        case_id=case_id,
        case_type="positive",
        passed=True,
        fabrication=False,
        recall_hit=None,
        failure_stage=None,
        failure_code=None,
        complexity="simple",
        latency_ms=1000,
        cost_usd=Decimal("0.01"),
        claims_integrity=_trivial_integrity(),
        socrata_successes=1,
        socrata_attempts=1,
    )


def _smoke_canonical_outcomes():
    """Los 10 case_ids canónicos del smoke dirigido (pruebas.md §4.4), todos en
    verde: base sobre la que las pruebas mutan un solo caso para aislar un
    fallo específico de la puerta de smoke."""

    return [
        _outcome("pilot-002-seguridad-homicidios", "positive", True),
        _outcome("pilot-003-salud-vigilancia", "positive", True),
        _outcome("pilot-005-empleo-publico", "positive", True),
        _outcome("pilot-013-app-dnp", "positive", True),
        _outcome("pilot-012-control-fiscal", "positive", True),
        _outcome("pilot-021-sensibilizacion-valle", "positive", True),
        _outcome("pilot-022-red-vial", "positive", True),
        _outcome("pilot-038-precipitacion", "positive", True),
        _outcome("pilot-045-negativo-dato-personal", "negative", True),
        _outcome("pilot-046-negativo-tiempo-real", "negative", True),
    ]


# --- A. Éxito y negativos -----------------------------------------------------


def test_success_rate_is_over_positives_only_not_all_cases() -> None:
    """30/40 positivos + 10/10 negativos = 75%, NO 80%."""

    aggregate = aggregate_metrics(_suite(30, 10))

    assert aggregate.positive_passed == 30
    assert aggregate.positive_total == 40
    assert aggregate.success_rate == 0.75  # no (30+10)/50 = 0.80
    assert aggregate.negative_success_rate == 1.0


def test_imperfect_negatives_block_even_when_positives_exceed_80pct() -> None:
    aggregate = aggregate_metrics(_suite(39, 9))  # positivos 97.5%, negativos 90%

    assert aggregate.success_rate >= 0.80
    verdict = evaluate_full_gate(aggregate)
    assert verdict.passed is False
    assert any("negativo" in reason for reason in verdict.blocking_reasons)


def test_thirty_of_forty_positives_never_reads_as_80_percent() -> None:
    aggregate = aggregate_metrics(_suite(30, 10))
    verdict = evaluate_full_gate(aggregate)

    assert verdict.passed is False
    assert any("80%" in reason or "RNF-002" in reason for reason in verdict.blocking_reasons)


# --- B. Integridad cuantitativa de claims ------------------------------------


def test_valid_claim_reproduces_and_integrity_holds() -> None:
    result = evaluate_claims_integrity(_valid_final())

    assert result.applicable is True
    assert result.reproducible_claim_count == 1
    assert result.claims_reproducible == 1.0
    assert result.orphan_figure_count == 0
    assert result.integrity_ok is True
    assert result.failure_codes == ()


def test_corruption_missing_evidence_fails() -> None:
    final = _valid_final()
    final["claims"][0]["evidence_id"] = str(uuid.uuid4())  # no existe en evidence
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "evidence_missing" in result.failure_codes


def test_corruption_row_out_of_range_fails() -> None:
    final = _valid_final()
    final["claims"][0]["source_row_indexes"] = [5]
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "row_out_of_range" in result.failure_codes


def test_corruption_unknown_column_fails() -> None:
    """T-617C-R2: una columna pública que no es clave de las filas NI puede
    resolverse vía SoQL (sin alias declarado en `_valid_final`) falla con el
    código específico `column_unresolvable`, no con el genérico anterior."""

    final = _valid_final()
    final["claims"][0]["columns"] = ["inexistente"]
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "column_unresolvable" in result.failure_codes


def test_corruption_raw_value_mismatch_fails() -> None:
    final = _valid_final()
    final["claims"][0]["raw_value"] = 999
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "raw_value_mismatch" in result.failure_codes


def test_corruption_display_value_mismatch_fails() -> None:
    final = _valid_final()
    final["claims"][0]["display_value"] = "999"
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "display_value_mismatch" in result.failure_codes


def test_corruption_source_hash_mismatch_fails() -> None:
    final = _valid_final()
    final["claims"][0]["source_hash"] = "sha256:" + "0" * 64
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "source_hash_mismatch" in result.failure_codes


def test_orphan_figure_in_narrative_breaks_coverage() -> None:
    final = _valid_final(summary="El total es 100 y la tasa fue del 87%.")
    result = evaluate_claims_integrity(final)

    assert result.orphan_figure_count >= 1
    assert result.claims_coverage < 1.0
    assert result.integrity_ok is False
    assert "orphan_figures" in result.failure_codes


def test_claims_integrity_does_not_use_expected_facts() -> None:
    """La integridad se certifica desde la evidencia reejecutada, no desde
    expected_facts del golden (que aquí no se pasan)."""

    result = evaluate_claims_integrity(_valid_final())
    assert result.reproducible_claim_count == 1


# --- B2. T-617C-R2: reproducción con nombres públicos reales (RF-212) -------
#
# Origen: smoke real fd2da0f1-94b6-47e4-8ddc-30926266f944 (T-617C-R1) obtuvo
# claims_reproducible=0.0% porque `final_answer.claims[].columns` ya persiste
# el nombre de columna fuente real (p. ej. "genero_hombre"), pero
# `evidence.rows` sigue indexada por el alias de ejecución SoQL ("dim_2").
# `_reproduce_one_claim` no reconstruía esa correspondencia. Estas pruebas
# fallan contra el baseline 8bfd7501ad9afb7341a1447f925df0c0735b0470 y pasan
# con T-617C-R2.


def _r1_final(
    *,
    soql: str = "SELECT genero_hombre AS dim_2 LIMIT 1",
    rows: tuple[dict, ...] = ({"dim_2": "764"},),
    execution_columns: tuple[str, ...] = ("dim_2",),
    column_field_names: dict[str, str] | None = None,
    claim_type: str = "direct",
    formula: dict | None = None,
    unit: str | None = None,
    rounding: int = 0,
) -> dict:
    """`final_answer` con un claim en formato T-617C-R1: `columns` público
    (nombre real) distinto de las claves de `evidence.rows` (alias de
    ejecución SoQL), reconstruible solo parseando `soql_query`."""

    mapping = (
        column_field_names
        if column_field_names is not None
        else dict.fromkeys(execution_columns, "genero_hombre")
    )
    evidence_id = str(uuid.uuid4())
    spec = ClaimSpec(
        claim_type=claim_type,
        description="Total",
        source_row_indexes=(0,),
        columns=execution_columns,
        column_field_names=mapping,
        formula=formula,
        unit=unit,
        rounding=rounding,
    )
    built = build_claims(
        EvidenceContext(dataset_id="abcd-1234", canonical_soql=soql, rows=rows),
        (spec,),
    ).claims[0]
    claim = {
        "claim_id": str(uuid.uuid4()),
        "claim": f"Total: {built.display_value}",
        "claim_type": claim_type,
        "evidence_id": evidence_id,
        "dataset_id": "abcd-1234",
        "source_row_indexes": list(built.source_row_indexes),
        "columns": list(built.public_columns),
        "formula": built.formula,
        "raw_value": (
            int(built.raw_value)
            if built.raw_value == built.raw_value.to_integral_value()
            else float(built.raw_value)
        ),
        "display_value": built.display_value,
        "unit": built.unit,
        "rounding": built.rounding,
        "source_hash": built.source_hash,
        "label": built.label,
        "label_status": built.label_status,
    }
    evidence = {
        "evidence_id": evidence_id,
        "dataset_id": "abcd-1234",
        "soql_query": soql,
        "rows": list(rows),
        "narrative": None,
    }
    return {
        "status": "completed",
        "claims": [claim],
        "evidence": [evidence],
        "summary": f"Total: {built.display_value}.",
    }


def test_r2_reproduces_public_real_column_name_against_alias_keyed_rows() -> None:
    """Requisito C.1: columns=["genero_hombre"], rows=[{"dim_2": "764"}],
    SoQL con `AS dim_2` -- reproduce al 100% con el hash v2.0.0."""

    final = _r1_final()
    result = evaluate_claims_integrity(final)

    assert result.applicable is True
    assert result.reproducible_claim_count == 1
    assert result.claims_reproducible == 1.0
    assert result.integrity_ok is True
    assert result.failure_codes == ()
    assert final["claims"][0]["source_hash"].startswith("sha256:")


def test_r2_derived_claim_with_alias_formula_and_public_columns_reproduces() -> None:
    """Requisito C.2: fórmula que referencia el alias interno (como la
    persiste el pipeline real, nunca traducida) junto con `columns` público
    real -- reproduce exactamente."""

    final = _r1_final(
        soql="SELECT matriculados AS dim_1, desertores AS dim_2 LIMIT 1",
        rows=({"dim_1": "1000", "dim_2": "84"},),
        execution_columns=("dim_1", "dim_2"),
        column_field_names={"dim_1": "matriculados", "dim_2": "desertores"},
        claim_type="derived",
        formula={"op": "div", "args": [{"col": "dim_2"}, {"col": "dim_1"}]},
        unit=None,
        rounding=4,
    )
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is True
    assert result.claims_reproducible == 1.0


def test_r2_count_star_sentinel_reproduces() -> None:
    """Requisito C.3: `count(*)` público como el centinela estructural
    (`__count__`, nunca texto inventado) reproduce correctamente."""

    final = _r1_final(
        soql="SELECT count(*) AS metric_count_1 LIMIT 1",
        rows=({"metric_count_1": "42"},),
        execution_columns=("metric_count_1",),
        column_field_names={"metric_count_1": "__count__"},
    )
    assert final["claims"][0]["columns"] == ["__count__"]
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is True
    assert result.claims_reproducible == 1.0


def test_r2_direct_path_still_works_when_public_column_is_already_a_row_key() -> None:
    """Requisito C.4: camino de compatibilidad -- claims persistidos antes de
    T-617C-R1 (o dobles que ya usan el nombre real como alias) con
    `columns` ya presente en las claves de `evidence.rows` siguen
    reproduciéndose sin tocar el SoQL."""

    result = evaluate_claims_integrity(_valid_final())

    assert result.integrity_ok is True
    assert result.claims_reproducible == 1.0


def test_r2_nonexistent_public_column_fails_deterministically() -> None:
    """Requisito C.5: una columna pública que no es clave de las filas ni
    tiene alias en el SoQL persistido falla, no se reproduce por accidente."""

    final = _r1_final()
    final["claims"][0]["columns"] = ["columna_que_no_existe"]
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "column_unresolvable" in result.failure_codes


def test_r2_invalid_soql_fails_safely_without_uncontrolled_exception() -> None:
    """Requisito C.6: un SoQL no parseable produce un código de fallo seguro,
    nunca una excepción sin controlar que interrumpa la evaluación completa."""

    final = _r1_final()
    final["evidence"][0]["soql_query"] = "ESTO NO ES SOQL ((("
    final["claims"][0]["columns"] = ["genero_hombre"]

    result = evaluate_claims_integrity(final)  # no debe lanzar

    assert result.integrity_ok is False
    assert "soql_unparseable" in result.failure_codes


def test_r2_ambiguous_alias_mapping_fails_instead_of_picking_last_silently() -> None:
    """Requisito C.7: dos alias distintos para el mismo nombre público real
    (p. ej. la misma columna seleccionada dos veces) deben fallar de forma
    determinista por ambigüedad, nunca resolverse tomando el último alias
    encontrado en silencio."""

    final = _r1_final(
        soql="SELECT genero_hombre AS dim_1, genero_hombre AS dim_2 LIMIT 1",
        rows=({"dim_1": "764", "dim_2": "764"},),
        execution_columns=("dim_1",),
        column_field_names={"dim_1": "genero_hombre"},
    )
    # El claim ya reproduce con dim_1; forzamos la ambigüedad estructural
    # directamente sobre el SoQL persistido, que es lo que _reproduce_one_claim
    # relee -- ambos alias mapean a "genero_hombre" en ese SoQL.
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "column_mapping_ambiguous" in result.failure_codes


def test_r2_tampered_raw_value_display_value_or_hash_still_fail() -> None:
    """Requisito C.8: manipular `raw_value`/`display_value`/`source_hash` de
    un claim en formato R1 sigue detectándose, igual que en el formato
    anterior (test_corruption_* ya cubre el formato directo)."""

    base = _r1_final()

    tampered_raw = json.loads(json.dumps(base))
    tampered_raw["claims"][0]["raw_value"] = 999
    assert evaluate_claims_integrity(tampered_raw).integrity_ok is False

    tampered_display = json.loads(json.dumps(base))
    tampered_display["claims"][0]["display_value"] = "999"
    assert evaluate_claims_integrity(tampered_display).integrity_ok is False

    tampered_hash = json.loads(json.dumps(base))
    tampered_hash["claims"][0]["source_hash"] = "sha256:" + "0" * 64
    assert evaluate_claims_integrity(tampered_hash).integrity_ok is False


# --- B3. T-617C-R2: `integridad_claims` bloquea el smoke -----------------------


def _smoke_canonical_outcomes_with_broken_claim(broken_case_id: str) -> list[CaseOutcome]:
    """Los 10 canónicos en verde salvo `broken_case_id`, cuya integridad de
    claims está rota (formato R1 con columna pública inexistente) aunque el
    caso siga `passed=True` -- exactamente el escenario real que produjo
    `claims_reproducible=0.0%` con `gate_passed=true` antes de T-617C-R2."""

    broken_final = _r1_final()
    broken_final["claims"][0]["columns"] = ["columna_que_no_existe"]
    broken_integrity = evaluate_claims_integrity(broken_final)
    assert broken_integrity.integrity_ok is False  # verificación de la propia fixture

    outcomes = []
    for outcome in _smoke_canonical_outcomes():
        if outcome.case_id == broken_case_id:
            outcomes.append(
                _outcome(
                    outcome.case_id,
                    outcome.case_type,
                    True,
                    integrity=broken_integrity,
                )
            )
        else:
            outcomes.append(outcome)
    return outcomes


def test_r2_smoke_with_broken_claims_integrity_cannot_pass() -> None:
    """Requisito C.9: los 10 canónicos, cardinalidad/negativos/sólidos
    perfectos, pero un caso con integridad de claims rota -- el smoke NO
    puede aprobar. Esto es exactamente lo que faltaba: antes de R2, ninguna
    métrica de `evaluate_smoke_gate` miraba `claims_integrity`."""

    outcomes = _smoke_canonical_outcomes_with_broken_claim("pilot-005-empleo-publico")
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    integrity_metric = next(m for m in smoke.metrics if m.name == "integridad_claims")
    assert integrity_metric.passed is False
    assert "pilot-005-empleo-publico" in (integrity_metric.reason or "")


def test_r2_smoke_with_full_claims_integrity_can_pass() -> None:
    """Requisito C.10: el mismo smoke, con integridad de claims completa en
    todos los casos, sí puede aprobar."""

    smoke = evaluate_smoke_gate(_smoke_canonical_outcomes())
    assert smoke.passed is True
    integrity_metric = next(m for m in smoke.metrics if m.name == "integridad_claims")
    assert integrity_metric.passed is True


def test_r2_other_smoke_metrics_remain_intact() -> None:
    """Requisito C.11: cardinalidad, negativos, positivos sólidos,
    infraestructura y fallos clasificados no cambiaron de comportamiento --
    solo se añadió `integridad_claims` como métrica nueva."""

    smoke = evaluate_smoke_gate(_smoke_canonical_outcomes())
    metric_names = {m.name for m in smoke.metrics}
    assert metric_names == {
        "cobertura_canónica",
        "negativos",
        "positivos_sólidos",
        "infraestructura",
        "fallos_clasificados",
        "integridad_claims",
    }
    for name in (
        "cobertura_canónica",
        "negativos",
        "positivos_sólidos",
        "infraestructura",
        "fallos_clasificados",
    ):
        metric = next(m for m in smoke.metrics if m.name == name)
        assert metric.passed is True


# --- C. Rendimiento y clasificación ------------------------------------------


def test_percentile_is_deterministic_nearest_rank() -> None:
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(values, 0.50) == 50
    assert percentile(values, 0.95) == 100
    assert percentile([42], 0.95) == 42
    assert percentile([], 0.95) is None


def test_classify_simple_requires_one_dataset_one_soql_no_exploration() -> None:
    base = {"evidence_count": 1, "query_count": 1, "exploration_count": 0}
    assert classify_run_complexity(base) == "simple"


def test_classify_multistep_when_any_signal_exceeds_simple() -> None:
    assert (
        classify_run_complexity({"evidence_count": 2, "query_count": 1, "exploration_count": 0})
        == "multistep"
    )
    assert (
        classify_run_complexity({"evidence_count": 1, "query_count": 2, "exploration_count": 0})
        == "multistep"
    )
    assert (
        classify_run_complexity({"evidence_count": 1, "query_count": 1, "exploration_count": 1})
        == "multistep"
    )


def test_average_cost_uses_deterministic_mean() -> None:
    outcomes = [
        _outcome("a", "positive", True, cost_usd=Decimal("0.02")),
        _outcome("b", "positive", True, cost_usd=Decimal("0.04")),
    ]
    aggregate = aggregate_metrics(outcomes)
    assert aggregate.avg_cost_usd == Decimal("0.03")


def test_p95_uses_complexity_partition() -> None:
    outcomes = [
        _outcome("s1", "positive", True, complexity="simple", latency_ms=5000),
        _outcome("s2", "positive", True, complexity="simple", latency_ms=8000),
        _outcome("m1", "positive", True, complexity="multistep", latency_ms=60000),
    ]
    aggregate = aggregate_metrics(outcomes)
    assert aggregate.latency_simple_p95_ms == 8000
    assert aggregate.latency_multistep_p95_ms == 60000


# --- D. Socrata ---------------------------------------------------------------


def test_socrata_success_rate_none_when_no_t5_calls() -> None:
    obs = [SimpleNamespace(output={"detail": "no t5"})]
    assert socrata_success_rate(obs) is None


def test_socrata_success_rate_counts_ok_and_transport_failures() -> None:
    obs = [
        SimpleNamespace(output={"ok": True, "rows": []}),
        SimpleNamespace(output={"ok": False, "error": {"code": "SOCRATA_TIMEOUT"}}),
        SimpleNamespace(output={"ok": False, "error": {"code": "SOQL_SYNTAX"}}),
    ]
    # 2 éxitos (ok + error no-transporte) sobre 3 llamadas T5
    assert socrata_success_rate(obs) == (2, 3)


# --- E. Veredicto de puerta ---------------------------------------------------


def test_full_gate_fails_on_single_unmet_threshold() -> None:
    # Todo perfecto salvo la latencia p95 simple: se fuerza sobre el umbral en
    # todas las corridas simples para que el percentil lo supere de verdad.
    outcomes = _suite(40, 10)
    for o in outcomes:
        if o.complexity == "simple":
            object.__setattr__(o, "latency_ms", 25_000)
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.latency_simple_p95_ms == 25_000
    assert verdict.passed is False
    assert any("20 s" in reason or "RNF-001" in reason for reason in verdict.blocking_reasons)


def test_full_gate_passes_when_all_conditions_met() -> None:
    aggregate = aggregate_metrics(_suite(40, 10))
    verdict = evaluate_full_gate(aggregate)

    assert verdict.passed is True
    assert verdict.blocking_reasons == ()


def test_avg_cost_over_threshold_blocks_full_gate() -> None:
    outcomes = _suite(40, 10)
    for o in outcomes:
        object.__setattr__(o, "cost_usd", AVG_COST_USD_THRESHOLD + Decimal("0.10"))
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert verdict.passed is False
    assert any("0,05" in reason or "RNF-009" in reason for reason in verdict.blocking_reasons)


def test_smoke_and_full_gates_are_distinct() -> None:
    """Mismo conjunto canónico de 10: el umbral completo falla (positivos <
    80%), pero el smoke pasa (10 canónicos, negativos 2/2, sólidos intactos,
    fallos clasificados)."""

    outcomes = _smoke_canonical_outcomes()
    # Los cuatro patrones diferenciados (no sólidos) fallan con etapa+código:
    # bajan los positivos a 4/8 = 50% pero no rompen la puerta de smoke.
    for i, o in enumerate(outcomes):
        if o.case_id in {
            "pilot-012-control-fiscal",
            "pilot-021-sensibilizacion-valle",
            "pilot-022-red-vial",
            "pilot-038-precipitacion",
        }:
            outcomes[i] = _outcome(o.case_id, "positive", False)

    full = evaluate_full_gate(aggregate_metrics(outcomes))
    smoke = evaluate_smoke_gate(outcomes)

    assert full.passed is False  # 4/8 positivos < 80%
    assert any("80%" in r or "RNF-002" in r for r in full.blocking_reasons)
    assert smoke.passed is True
    assert full.mode == "full"
    assert smoke.mode == "smoke"


def test_smoke_gate_blocks_when_solid_positive_regresses() -> None:
    # Base canónica de 10 en verde; solo retrocede un positivo sólido, para
    # aislar esa razón bloqueante de la cobertura canónica.
    outcomes = _smoke_canonical_outcomes()
    for i, o in enumerate(outcomes):
        if o.case_id == "pilot-002-seguridad-homicidios":
            outcomes[i] = _outcome(o.case_id, "positive", False)  # sólido retrocede
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("sólidos" in reason for reason in smoke.blocking_reasons)
    # La cobertura canónica sigue satisfecha: el fallo es específicamente el
    # retroceso de un sólido, no una ausencia de casos.
    assert not any("faltan" in reason for reason in smoke.blocking_reasons)


def test_smoke_gate_blocks_when_a_failure_lacks_stage_or_code() -> None:
    # Base canónica de 10; se reemplaza un diferenciado por una corrida fallida
    # sin etapa ni código (muda), conservando el case_id canónico.
    outcomes = _smoke_canonical_outcomes()
    for i, o in enumerate(outcomes):
        if o.case_id == "pilot-012-control-fiscal":
            outcomes[i] = CaseOutcome(
                case_id="pilot-012-control-fiscal",
                case_type="positive",
                passed=False,
                fabrication=False,
                recall_hit=False,
                failure_stage=None,  # sin etapa
                failure_code=None,  # sin código
                complexity="simple",
                latency_ms=1000,
                cost_usd=Decimal("0.01"),
                claims_integrity=_trivial_integrity(),
                socrata_successes=0,
                socrata_attempts=0,
            )
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("etapa/código" in reason for reason in smoke.blocking_reasons)


# --- F. Regresiones T-617B0-R (falsos positivos reproducidos por Codex) -------


def test_full_gate_fails_when_latency_and_cost_are_none() -> None:
    """Codex #1: latencia y costo None NO pueden aprobar la puerta completa;
    la incompletitud de medición produce FAIL con razón explícita."""

    outcomes = _suite(40, 10)
    for o in outcomes:
        object.__setattr__(o, "latency_ms", None)
        object.__setattr__(o, "cost_usd", None)
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.latency_simple_p95_ms is None
    assert aggregate.avg_cost_usd is None
    assert verdict.passed is False
    assert any("latencia" in r for r in verdict.blocking_reasons)
    assert any("costo" in r for r in verdict.blocking_reasons)


def test_full_gate_fails_when_multistep_sample_missing() -> None:
    """Sin muestra multipaso medible el p95 multipaso es None y NO aprueba: la
    puerta completa exige muestra válida en ambas particiones (RNF-001)."""

    outcomes = [_outcome(f"pos-{i}", "positive", True, complexity="simple") for i in range(40)]
    outcomes += [_outcome(f"neg-{i}", "negative", True, complexity="simple") for i in range(10)]
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.multistep_sample_count == 0
    assert aggregate.latency_multistep_p95_ms is None
    assert verdict.passed is False
    assert any("multipaso" in r for r in verdict.blocking_reasons)


def test_recall_true_plus_none_is_never_100_percent() -> None:
    """Codex #2: un positivo True + uno None nunca produce recall@10 = 100%.
    None cuenta como miss sobre todos los positivos, jamás se excluye."""

    outcomes = [
        _outcome("p-true", "positive", True, recall_hit=True),
        _positive_recall_none("p-none"),
    ]
    aggregate = aggregate_metrics(outcomes)

    assert aggregate.positive_total == 2
    assert aggregate.recall_hits == 1
    assert aggregate.recall_measured_count == 1  # se registra medido vs total
    assert aggregate.recall_at_10 == 0.5  # 1/2, NO 1/1
    assert aggregate.recall_at_10 != 1.0


def test_recall_counts_none_as_miss_over_all_positives() -> None:
    """El denominador de recall@10 es el total de positivos, no solo los
    medidos: 3 True + 1 None = 75%, por debajo del umbral del 85%."""

    outcomes = [
        _outcome("a", "positive", True, recall_hit=True),
        _outcome("b", "positive", True, recall_hit=True),
        _outcome("c", "positive", True, recall_hit=True),
        _positive_recall_none("d"),
    ]
    aggregate = aggregate_metrics(outcomes)

    assert aggregate.recall_at_10 == 0.75
    verdict = evaluate_full_gate(aggregate)
    assert any("recall" in r or "RNF-004" in r for r in verdict.blocking_reasons)


def test_smoke_gate_fails_with_only_two_negatives() -> None:
    """Codex #3: ejecutar solo los dos negativos NO puede aprobar el smoke;
    faltan los ocho positivos canónicos (cobertura canónica incompleta)."""

    outcomes = [
        _outcome("pilot-045-negativo-dato-personal", "negative", True),
        _outcome("pilot-046-negativo-tiempo-real", "negative", True),
    ]
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("faltan" in reason for reason in smoke.blocking_reasons)


def test_smoke_gate_passes_with_exactly_the_ten_canonical() -> None:
    """Con exactamente los 10 canónicos en verde el smoke aprueba."""

    smoke = evaluate_smoke_gate(_smoke_canonical_outcomes())

    assert smoke.passed is True
    assert smoke.blocking_reasons == ()


# --- H. Regresiones T-617B0-R3 (falla de proveedor vs regresión semántica) --


def _infra_outcome(case_id: str, case_type: str = "positive") -> CaseOutcome:
    """Un CaseOutcome fallido cuya causa es infraestructura/proveedor, no una
    regresión semántica (eval.diagnostics failure_owner='infrastructure')."""

    return CaseOutcome(
        case_id=case_id,
        case_type=case_type,
        passed=False,
        fabrication=False,
        recall_hit=False if case_type == "positive" else None,
        failure_stage="planning",
        failure_code="provider_error",
        complexity="multistep",
        latency_ms=1000,
        cost_usd=Decimal("0.01"),
        claims_integrity=_trivial_integrity(),
        socrata_successes=0,
        socrata_attempts=0,
        infrastructure_failure=True,
    )


def test_smoke_gate_blocks_on_infra_failure_without_counting_it_as_semantic_regression() -> None:
    """T-617B0-R3 #2: los 10 canónicos con un sólido afectado por
    provider_error NUNCA pasan, pero ese caso no aparece como retroceso
    semántico si el resto de sólidos sigue en verde; el bloqueo viene de la
    métrica de infraestructura."""

    outcomes = _smoke_canonical_outcomes()
    for i, o in enumerate(outcomes):
        if o.case_id == "pilot-005-empleo-publico":
            outcomes[i] = _infra_outcome(o.case_id)
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    solid_metric = next(m for m in smoke.metrics if m.name == "positivos_sólidos")
    assert solid_metric.passed is True  # el sólido afectado no cuenta como retroceso
    assert not any("sólidos" in reason for reason in smoke.blocking_reasons)
    infra_metric = next(m for m in smoke.metrics if m.name == "infraestructura")
    assert infra_metric.passed is False
    assert any("infraestructura" in reason for reason in smoke.blocking_reasons)
    assert any("pilot-005-empleo-publico" in reason for reason in smoke.blocking_reasons)


def _structured_output_invalid_outcome(case_id: str) -> CaseOutcome:
    """Un CaseOutcome fallido por STRUCTURED_OUTPUT_INVALID: NO es
    infraestructura/proveedor (contracts/api-rest.md §4, eval.diagnostics
    failure_owner='agent'); `infrastructure_failure` es False."""

    return CaseOutcome(
        case_id=case_id,
        case_type="positive",
        passed=False,
        fabrication=False,
        recall_hit=False,
        failure_stage="synthesis",
        failure_code="structured_output_invalid",
        complexity="multistep",
        latency_ms=1000,
        cost_usd=Decimal("0.01"),
        claims_integrity=_trivial_integrity(),
        socrata_successes=0,
        socrata_attempts=0,
        infrastructure_failure=False,
    )


def test_smoke_gate_structured_output_invalid_still_blocks_as_semantic_regression() -> None:
    """T-617B0-R3A #4 (hallazgo de auditoría #2): STRUCTURED_OUTPUT_INVALID NO
    se clasifica como infraestructura/proveedor (contracts/api-rest.md §4):
    si afecta un positivo sólido, SIGUE contando como regresión semántica
    bloqueante en `positivos_sólidos`, a diferencia de `provider_error`."""

    outcomes = _smoke_canonical_outcomes()
    for i, o in enumerate(outcomes):
        if o.case_id == "pilot-005-empleo-publico":
            outcomes[i] = _structured_output_invalid_outcome(o.case_id)
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    solid_metric = next(m for m in smoke.metrics if m.name == "positivos_sólidos")
    assert solid_metric.passed is False  # SÍ cuenta como retroceso semántico
    assert any("sólidos" in reason for reason in smoke.blocking_reasons)
    infra_metric = next(m for m in smoke.metrics if m.name == "infraestructura")
    assert infra_metric.passed is True  # no es una falla de infraestructura


def test_full_gate_blocks_on_any_infrastructure_failure_even_with_perfect_metrics() -> None:
    """T-617B0-R3 #3: una puerta full con cualquier corrida de infraestructura
    tampoco puede PASS, aunque el resto de la puerta sea perfecto (40/40
    positivos, 10/10 negativos, cardinalidad completa)."""

    outcomes = _suite(40, 10)
    object.__setattr__(outcomes[0], "infrastructure_failure", True)
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.success_rate == 1.0
    assert aggregate.negative_success_rate == 1.0
    assert aggregate.infrastructure_failure_count == 1
    assert verdict.passed is False
    infra_metric = next(m for m in verdict.metrics if m.name == "infraestructura")
    assert infra_metric.passed is False
    assert any("infraestructura" in reason for reason in verdict.blocking_reasons)


def test_full_gate_passes_with_zero_infrastructure_failures_and_all_conditions_met() -> None:
    """Complemento del anterior: sin fallas de infraestructura, la puerta
    completa sigue aprobando igual que antes de T-617B0-R3 (no-daño)."""

    aggregate = aggregate_metrics(_suite(40, 10))
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.infrastructure_failure_count == 0
    infra_metric = next(m for m in verdict.metrics if m.name == "infraestructura")
    assert infra_metric.passed is True
    assert verdict.passed is True


def test_smoke_gate_still_blocks_on_genuine_semantic_regression_of_a_solid() -> None:
    """T-617B0-R3 #4: una falla SEMÁNTICA real de un sólido (sin
    infrastructure_failure) sigue siendo una regresión bloqueante, distinta
    de la métrica de infraestructura."""

    outcomes = _smoke_canonical_outcomes()
    for i, o in enumerate(outcomes):
        if o.case_id == "pilot-003-salud-vigilancia":
            outcomes[i] = _outcome(o.case_id, "positive", False)  # regresión semántica genuina
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    solid_metric = next(m for m in smoke.metrics if m.name == "positivos_sólidos")
    assert solid_metric.passed is False
    assert any("sólidos" in reason for reason in smoke.blocking_reasons)
    infra_metric = next(m for m in smoke.metrics if m.name == "infraestructura")
    assert infra_metric.passed is True  # ninguna falla de infraestructura aquí


def test_smoke_gate_passes_cleanly_with_no_infrastructure_field_regression() -> None:
    """T-617B0-R3 #5: un smoke limpio (comportamiento preexistente) conserva
    su PASS; el nuevo campo infrastructure_failure por defecto es False y no
    introduce ninguna razón bloqueante nueva."""

    smoke = evaluate_smoke_gate(_smoke_canonical_outcomes())

    assert smoke.passed is True
    assert smoke.blocking_reasons == ()
    infra_metric = next(m for m in smoke.metrics if m.name == "infraestructura")
    assert infra_metric.passed is True


def test_smoke_gate_fails_when_extra_noncanonical_case_present() -> None:
    """Añadir un caso no canónico invalida el smoke antes del veredicto."""

    outcomes = _smoke_canonical_outcomes()
    outcomes.append(_outcome("pilot-099-intruso", "positive", True))
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("sobran" in reason for reason in smoke.blocking_reasons)


def test_classify_zero_queries_is_not_simple() -> None:
    """Fix #4: una corrida con cero consultas o cero evidencias (abstención,
    fallo o caso no aplicable) NUNCA es 'simple'; cae en 'multistep'."""

    assert (
        classify_run_complexity({"evidence_count": 0, "query_count": 0, "exploration_count": 0})
        == "multistep"
    )
    assert (
        classify_run_complexity({"evidence_count": 1, "query_count": 0, "exploration_count": 0})
        == "multistep"
    )
    assert (
        classify_run_complexity({"evidence_count": 0, "query_count": 1, "exploration_count": 0})
        == "multistep"
    )
    # el caso canónico 1 dataset / 1 SoQL / 0 exploraciones sigue siendo simple
    assert (
        classify_run_complexity({"evidence_count": 1, "query_count": 1, "exploration_count": 0})
        == "simple"
    )


# --- G. Regresiones T-617B0-R2 (falsos positivos mecánicos remanentes) --------


@pytest.mark.parametrize("positives,negatives", [(1, 1), (8, 2)])
def test_full_gate_rejects_perfect_partial_sample(positives: int, negatives: int) -> None:
    """T-617B0-R2 #1: una muestra parcial perfecta (2 o 10 resultados) NUNCA
    puede certificarse como puerta completa. La cardinalidad de suite bloquea
    aunque todas las métricas observadas sean perfectas."""

    outcomes = _suite(positives, negatives, positives=positives, negatives=negatives)
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    # Métricas observadas perfectas: sin la guarda de cardinalidad, aprobaría.
    assert aggregate.success_rate == 1.0
    assert aggregate.negative_success_rate == 1.0
    assert aggregate.measured_total == positives + negatives
    assert verdict.passed is False
    assert any("puerta completa" in reason for reason in verdict.blocking_reasons)


def test_full_gate_cardinality_passes_with_exactly_40_positives_10_negatives() -> None:
    """La puerta completa aprueba con exactamente 40 positivos + 10 negativos
    únicos cuando todas las demás métricas cumplen (50 case_ids distintos)."""

    aggregate = aggregate_metrics(_suite(40, 10))
    verdict = evaluate_full_gate(aggregate)

    cardinality = next(m for m in verdict.metrics if m.name == "cardinalidad_suite")
    assert aggregate.distinct_case_id_count == 50
    assert cardinality.passed is True
    assert verdict.passed is True
    assert verdict.blocking_reasons == ()


def test_full_gate_rejects_duplicated_case_ids_even_with_fifty_results() -> None:
    """50 resultados pero con un case_id repetido (49 únicos) NO es la suite
    completa: la unicidad de case_ids es parte de la cardinalidad."""

    outcomes = _suite(40, 10)
    object.__setattr__(outcomes[1], "case_id", outcomes[0].case_id)  # colapsa 2 IDs en 1
    aggregate = aggregate_metrics(outcomes)
    verdict = evaluate_full_gate(aggregate)

    assert aggregate.measured_total == 50
    assert aggregate.distinct_case_id_count == 49
    assert verdict.passed is False
    assert any("únicos" in reason for reason in verdict.blocking_reasons)


def test_smoke_gate_fails_with_duplicated_canonical_case() -> None:
    """T-617B0-R2 #2: los 10 canónicos más la repetición de uno (11 resultados,
    10 IDs únicos) NO pueden aprobar el smoke; se ejecutó un caso dos veces."""

    outcomes = _smoke_canonical_outcomes()
    outcomes.append(_outcome("pilot-002-seguridad-homicidios", "positive", True))
    smoke = evaluate_smoke_gate(outcomes)

    assert len(outcomes) == 11
    assert len({o.case_id for o in outcomes}) == 10
    assert smoke.passed is False
    assert any("duplicados" in reason for reason in smoke.blocking_reasons)


# Preflight puro de selección (fail-fast antes de gastar cuota).


def _ns_cases(pairs):
    return [SimpleNamespace(case_id=cid, case_type=ctype) for cid, ctype in pairs]


def _ctype(case_id: str) -> str:
    return "negative" if "negativo" in case_id else "positive"


def _smoke_canonical_cases():
    return _ns_cases((cid, _ctype(cid)) for cid in sorted(SMOKE_CANONICAL_IDS))


def test_validate_gate_selection_rejects_unknown_mode() -> None:
    with pytest.raises(RuntimeError, match="gate_mode desconocido"):
        validate_gate_selection([], "weird")


@pytest.mark.parametrize("positives,negatives", [(1, 1), (40, 9), (39, 10)])
def test_validate_gate_selection_full_rejects_incompatible(positives: int, negatives: int) -> None:
    cases = _ns_cases(
        [(f"p{i}", "positive") for i in range(positives)]
        + [(f"n{i}", "negative") for i in range(negatives)]
    )
    with pytest.raises(RuntimeError, match="puerta full"):
        validate_gate_selection(cases, "full")


def test_validate_gate_selection_full_rejects_duplicates() -> None:
    cases = _ns_cases(
        [(f"p{i}", "positive") for i in range(40)] + [(f"n{i}", "negative") for i in range(10)]
    )
    cases[1].case_id = cases[0].case_id  # 50 casos pero 49 únicos
    with pytest.raises(RuntimeError, match="duplicados"):
        validate_gate_selection(cases, "full")


def test_validate_gate_selection_full_accepts_complete_suite() -> None:
    cases = _ns_cases(
        [(f"p{i}", "positive") for i in range(40)] + [(f"n{i}", "negative") for i in range(10)]
    )
    validate_gate_selection(cases, "full")  # no lanza


def test_validate_gate_selection_smoke_rejects_missing_and_duplicate() -> None:
    only_one = _ns_cases([("pilot-045-negativo-dato-personal", "negative")])
    with pytest.raises(RuntimeError, match="faltan"):
        validate_gate_selection(only_one, "smoke")

    dup = _smoke_canonical_cases()
    dup.append(dup[0])
    with pytest.raises(RuntimeError, match="duplicados"):
        validate_gate_selection(dup, "smoke")


def test_validate_gate_selection_smoke_accepts_exactly_ten_canonical() -> None:
    validate_gate_selection(_smoke_canonical_cases(), "smoke")  # no lanza


# --- Persistencia y reportes --------------------------------------------------


def test_aggregate_metrics_are_persisted_to_all_columns() -> None:
    record = SimpleNamespace()
    aggregate = aggregate_metrics(_suite(40, 10))
    apply_aggregate_metrics(record, aggregate)

    assert record.success_rate == Decimal("1")
    assert record.recall_at_10 is not None
    assert record.fabrication_count == 0
    assert record.orphan_figures_count == 0
    assert record.claims_coverage is None or isinstance(record.claims_coverage, Decimal)
    assert record.latency_p50_ms is not None
    assert record.latency_p95_ms is not None
    assert record.latency_simple_p95_ms is not None
    assert record.avg_cost_usd is not None


def test_report_summary_shows_numerator_denominator_and_thresholds() -> None:
    aggregate = aggregate_metrics(_suite(30, 10))
    verdict = evaluate_full_gate(aggregate)
    text = "\n".join(_gate_summary_lines(aggregate, verdict))

    assert "Positivos aprobados: 30/40" in text
    assert "Negativos aprobados: 10/10" in text
    assert ">= 80%" in text  # umbral visible
    assert "FAIL" in text  # estado por métrica


def test_case_result_metrics_carry_no_new_sensitive_text() -> None:
    """eval_case_results.metrics no debe ganar contenido textual sensible:
    el snapshot de integridad de claims solo tiene conteos/códigos."""

    final = _valid_final(summary="El total confidencial es 100.")
    integrity = evaluate_claims_integrity(final)
    from eval.loader import GoldenCase
    from eval.metrics import assess_case

    case = GoldenCase("p", "positive", "q", ("abcd-1234",), (), 1, "n")
    model = _case_result_model(
        eval_run_id=uuid.uuid4(),
        case_db_id=uuid.uuid4(),
        agent_run_id=None,
        final=final,
        assessment=assess_case(case, final),
        stage_diagnostics={"failure_stage": None},
        claims_integrity=integrity,
    )
    snapshot = model.metrics["claims_integrity"]
    serialized = json.dumps(snapshot, ensure_ascii=False)

    assert "confidencial" not in serialized
    assert "narrative" not in serialized
    # solo tipos primitivos y códigos enumerados
    assert set(snapshot).issuperset({"claim_count", "claims_reproducible", "failure_codes"})
    for code in snapshot["failure_codes"]:
        assert isinstance(code, str)
