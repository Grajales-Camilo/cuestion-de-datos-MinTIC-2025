"""Pruebas deterministas de la instrumentación de puerta (T-617B0).

No ejecutan LLM, red ni base de datos: operan sobre estructuras materializadas.
Demuestran los huecos cerrados y sus bordes.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.quality.claims import ClaimSpec, EvidenceContext, build_claims
from eval.gate import (
    AVG_COST_USD_THRESHOLD,
    CaseOutcome,
    ClaimsIntegrityAssessment,
    aggregate_metrics,
    classify_run_complexity,
    evaluate_claims_integrity,
    evaluate_full_gate,
    evaluate_smoke_gate,
    percentile,
    socrata_success_rate,
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
    for i in range(positives):
        outcomes.append(_outcome(f"pos-{i}", "positive", i < positives_passed))
    for i in range(negatives):
        passed = i < negatives_passed
        outcomes.append(_outcome(f"neg-{i}", "negative", passed, fabrication=not passed))
    return outcomes


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
    final = _valid_final()
    final["claims"][0]["columns"] = ["inexistente"]
    result = evaluate_claims_integrity(final)

    assert result.integrity_ok is False
    assert "not_reproducible" in result.failure_codes


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
    """Mismo conjunto: el umbral completo falla (positivos < 80%), pero el
    smoke pasa (negativos 2/2, sólidos intactos, fallos clasificados)."""

    outcomes = [
        _outcome("pilot-045-negativo-dato-personal", "negative", True),
        _outcome("pilot-046-negativo-tiempo-real", "negative", True),
        _outcome("pilot-002-seguridad-homicidios", "positive", True),
        _outcome("pilot-003-salud-vigilancia", "positive", True),
        _outcome("pilot-005-empleo-publico", "positive", True),
        _outcome("pilot-013-app-dnp", "positive", True),
    ]
    # seis positivos no sólidos que fallan con etapa+código
    for i in range(6):
        outcomes.append(_outcome(f"otro-{i}", "positive", False))

    full = evaluate_full_gate(aggregate_metrics(outcomes))
    smoke = evaluate_smoke_gate(outcomes)

    assert full.passed is False  # 4/10 positivos < 80%
    assert smoke.passed is True
    assert full.mode == "full"
    assert smoke.mode == "smoke"


def test_smoke_gate_blocks_when_solid_positive_regresses() -> None:
    outcomes = [
        _outcome("pilot-045-negativo-dato-personal", "negative", True),
        _outcome("pilot-046-negativo-tiempo-real", "negative", True),
        _outcome("pilot-002-seguridad-homicidios", "positive", False),  # sólido retrocede
        _outcome("pilot-003-salud-vigilancia", "positive", True),
        _outcome("pilot-005-empleo-publico", "positive", True),
        _outcome("pilot-013-app-dnp", "positive", True),
    ]
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("sólidos" in reason for reason in smoke.blocking_reasons)


def test_smoke_gate_blocks_when_a_failure_lacks_stage_or_code() -> None:
    outcomes = [
        _outcome("pilot-045-negativo-dato-personal", "negative", True),
        _outcome("pilot-046-negativo-tiempo-real", "negative", True),
        CaseOutcome(
            case_id="mudo",
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
        ),
    ]
    smoke = evaluate_smoke_gate(outcomes)

    assert smoke.passed is False
    assert any("etapa/código" in reason for reason in smoke.blocking_reasons)


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
