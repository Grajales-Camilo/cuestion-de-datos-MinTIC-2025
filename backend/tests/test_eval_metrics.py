from __future__ import annotations

import pytest

from eval.diagnostics import StageObservation, build_stage_diagnostics
from eval.loader import GoldenCase
from eval.metrics import assess_case, recall_hit_at_10


def _positive_case(expected_facts=(), *, case_id="p") -> GoldenCase:
    return GoldenCase(case_id, "positive", "q", ("abcd-1234",), expected_facts, 1, "n")


def test_positive_requires_completed_answer_with_expected_dataset() -> None:
    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"municipio": "Zona Bananera", "tasa": "2.44"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.passed is True
    assert result.expected_dataset_hit is True
    assert result.facts_verified is True


def test_positive_fails_when_expected_facts_do_not_match_tolerance() -> None:
    """Acertar el dataset no basta: la cifra real debe coincidir con expected_value."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"municipio": "Zona Bananera", "tasa": "9.99"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.expected_dataset_hit is True
    assert result.facts_verified is False
    assert result.passed is False


def test_expected_fact_mismatch_does_not_blame_golden_without_audit() -> None:
    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        )
    )
    final = {
        "status": "completed",
        "evidence": [
            {
                "dataset_id": "abcd-1234",
                "rows": [{"municipio": "Zona Bananera", "tasa": "9.99"}],
            }
        ],
        "claims": [{"display_value": "9.99"}],
        "usage": {},
    }

    diagnostics = build_stage_diagnostics(
        case,
        final,
        assess_case(case, final),
        [
            StageObservation(
                "synthesize",
                {
                    "retrieved_dataset_ids": ["abcd-1234"],
                    "attempted_dataset_ids": ["abcd-1234"],
                },
                {},
            )
        ],
    )

    assert diagnostics["failure_code"] == "expected_fact_not_found"
    assert diagnostics["failure_owner"] == "undetermined"


_RABIES_EVENT = "AGRESIONES POR ANIMALES POTENCIALMENTE TRANSMISORES DE RABIA"


def test_positive_matches_a_metric_column_renamed_by_the_llm_pilot_003_style() -> None:
    """Regresión real (pilot-003-salud-vigilancia, 2026-07-12, run_ids
    16903813-.../b65a9eb9-.../b96c1a04-.../be2e0b5f-...): el LLM generó su
    propio SoQL y nombró la columna agregada `total_casos` en vez de
    `total_reportes`. Aprueba porque `total_reportes` es una MÉTRICA (valor
    esperado numérico) y queda exactamente una columna numérica sin
    resolver tras calzar la dimensión `nombre_evento` por nombre exacto --
    sin declarar ningún alias específico de este caso."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"nombre_evento": _RABIES_EVENT, "total_reportes": "1470739"},
                "tolerance": 0,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"nombre_evento": _RABIES_EVENT, "total_casos": "1470739"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.facts_verified is True
    assert result.passed is True


def test_positive_matches_a_metric_column_renamed_by_the_llm_pilot_002_style() -> None:
    """Regresión real (pilot-002-seguridad-homicidios, 2026-07-12, run_id
    e0250b8a-...): mismo problema de alias que pilot-003, con nombres de
    columna esperado (`total`) y real (`total_homicidios`) completamente
    distintos -- confirma que la política es general (por tipo de valor) y
    no una lista de alias por caso, que habría dejado este caso sin cubrir."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"departamento": "VALLE DEL CAUCA", "total": "66723"},
                "tolerance": 0,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"departamento": "VALLE DEL CAUCA", "total_homicidios": "66723"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.facts_verified is True
    assert result.passed is True


def test_positive_restores_deterministic_dimension_alias_from_rendered_soql() -> None:
    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"departamento": "VALLE DEL CAUCA", "total": "66723"},
                "tolerance": 0,
            },
        ),
    )

    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "soql_query": (
                        "SELECT departamento AS dim_1, sum(cantidad) AS metric_sum_1 "
                        "GROUP BY departamento ORDER BY metric_sum_1 DESC LIMIT 1 OFFSET 0"
                    ),
                    "rows": [{"dim_1": "VALLE DEL CAUCA", "metric_sum_1": "66723"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.facts_verified is True
    assert result.passed is True


def test_dimension_key_never_falls_back_to_a_differently_named_column() -> None:
    """Una dimensión (valor esperado de texto) exige coincidencia EXACTA de
    nombre de columna -- nunca se adivina, aunque el mismo valor aparezca
    bajo otro nombre de columna. Solo las métricas (valor numérico)
    toleran un alias no declarado."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    # "ciudad" (no "municipio") trae el mismo valor de texto.
                    "rows": [{"ciudad": "Zona Bananera", "tasa": "2.44"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.facts_verified is False
    assert result.passed is False


def test_two_metrics_cannot_both_claim_the_same_single_matching_column() -> None:
    """Si dos métricas esperadas coinciden por valor con la MISMA (y única)
    columna sobrante, ninguna puede "ganársela" en silencio -- se rechaza en
    vez de adivinar cuál de las dos es la correcta."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"total_pagos": "100", "total_compromisos": "100"},
                "tolerance": 0,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [{"dataset_id": "abcd-1234", "rows": [{"total": "100"}]}],
            "claims": [],
        },
    )

    assert result.facts_verified is False
    assert result.passed is False


def test_metric_with_no_matching_column_at_all_does_not_pass() -> None:
    """Una métrica cuyo valor no aparece en ninguna columna numérica
    sobrante debe fallar -- no hay nada que adivinar."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"departamento": "VALLE DEL CAUCA", "total": "66723"},
                "tolerance": 0,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"departamento": "VALLE DEL CAUCA", "total_homicidios": "1"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.facts_verified is False
    assert result.passed is False


def test_negative_fails_when_it_returns_evidence() -> None:
    case = GoldenCase("n", "negative", "q", (), (), 2, "n")
    result = assess_case(
        case,
        {"status": "no_evidence", "evidence": [{"dataset_id": "abcd-1234"}], "claims": []},
    )

    assert result.passed is False
    assert result.fabrication is True
    assert result.recall_hit is None


def test_collect_orphan_figures_are_reported_on_the_assessment() -> None:
    case = _positive_case()
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [{"dataset_id": "abcd-1234", "rows": []}],
            "claims": [{"display_value": "10", "evidence_id": "e1"}],
            "summary": "La tasa fue del 87%, muy por encima del 10 esperado.",
        },
    )

    assert "87" in "".join(result.orphan_figures)


def test_recall_hit_at_10_true_when_expected_dataset_in_search_results() -> None:
    case = _positive_case()
    assert recall_hit_at_10(case, ["other-id", "abcd-1234"]) is True
    assert recall_hit_at_10(case, ["other-id"]) is False


def test_recall_hit_at_10_is_none_for_negative_cases() -> None:
    case = GoldenCase("n", "negative", "q", (), (), 2, "n")
    assert recall_hit_at_10(case, ["abcd-1234"]) is None


def _failed_assessment(*, expected_hit=False, facts_verified=False) -> object:
    return assess_case(
        _positive_case(),
        {
            "status": "no_evidence",
            "evidence": ([{"dataset_id": "abcd-1234", "rows": []}] if expected_hit else []),
            "claims": [],
        },
    )


def test_diagnostics_classifies_expected_dataset_not_retrieved() -> None:
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        {"status": "no_evidence", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
        [StageObservation("tool:buscar_catalogo", {}, {"results": [{"dataset_id": "other"}]})],
    )

    assert diagnostics["failure_stage"] == "retrieval"
    assert diagnostics["failure_code"] == "expected_dataset_not_retrieved"
    assert diagnostics["retrieved_dataset_ids"] == ["other"]


def test_diagnostics_distinguishes_retrieved_but_not_attempted() -> None:
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        {"status": "no_evidence", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
        [
            StageObservation(
                "retrieve_candidates", {"retrieved_dataset_ids": ["other", "abcd-1234"]}, {}
            )
        ],
    )

    assert diagnostics["failure_code"] == "expected_dataset_not_attempted"
    assert diagnostics["expected_dataset_rank"] == 2


def test_diagnostics_classifies_invalid_plan_with_canonical_errors() -> None:
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        {"status": "no_evidence", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
        [
            StageObservation(
                "validate_plan",
                {
                    "retrieved_dataset_ids": ["abcd-1234"],
                    "attempted_dataset_ids": ["abcd-1234"],
                    "plan_validation_errors": ["unknown_column"],
                },
                {},
            )
        ],
    )

    assert diagnostics["failure_stage"] == "plan_validation"
    assert diagnostics["failure_code"] == "plan_invalid"
    assert diagnostics["plan_validation_errors"] == ["unknown_column"]


def test_diagnostics_classifies_zero_rows_after_query_execution() -> None:
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        {"status": "no_evidence", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
        [
            StageObservation(
                "execute_query",
                {
                    "retrieved_dataset_ids": ["abcd-1234"],
                    "attempted_dataset_ids": ["abcd-1234"],
                },
                {},
            )
        ],
    )

    assert diagnostics["failure_code"] == "zero_rows"


def test_diagnostics_classifies_rejected_claims() -> None:
    final = {
        "status": "no_evidence",
        "evidence": [{"dataset_id": "abcd-1234", "rows": [{"total": 1}]}],
        "claims": [],
        "usage": {},
    }
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        final,
        assess_case(_positive_case(), final),
        [
            StageObservation(
                "derive_claims",
                {
                    "retrieved_dataset_ids": ["abcd-1234"],
                    "attempted_dataset_ids": ["abcd-1234"],
                },
                {},
            )
        ],
    )

    assert diagnostics["failure_code"] == "claims_rejected"


def test_diagnostics_classifies_rejected_evidence() -> None:
    final = {
        "status": "no_evidence",
        "evidence": [{"dataset_id": "other-id", "rows": [{"total": 1}]}],
        "claims": [],
        "usage": {},
    }
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        final,
        assess_case(_positive_case(), final),
        [
            StageObservation(
                "validate_quality",
                {
                    "retrieved_dataset_ids": ["abcd-1234", "other-id"],
                    "attempted_dataset_ids": ["abcd-1234"],
                },
                {},
            )
        ],
    )

    assert diagnostics["failure_stage"] == "evidence_quality"
    assert diagnostics["failure_code"] == "evidence_not_eligible"


def test_diagnostics_marks_ambiguous_golden_as_golden_owned() -> None:
    ambiguous_case = _positive_case(expected_facts=({"description": "sin valor"},))
    diagnostics = build_stage_diagnostics(
        ambiguous_case,
        {"status": "no_evidence", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
    )

    assert diagnostics["failure_code"] == "ambiguous_golden"
    assert diagnostics["failure_owner"] == "golden"


def test_diagnostics_classifies_harness_exception_as_infrastructure() -> None:
    """T-617B0-R3A: una excepción del arnés de evaluación (`infrastructure_error`,
    p. ej. un `TimeoutError` de la propia conexión del evaluador) bloquea
    como infraestructura, no como regresión semántica del agente."""

    diagnostics = build_stage_diagnostics(
        _positive_case(),
        {"status": "eval_error", "evidence": [], "claims": [], "usage": {}},
        _failed_assessment(),
        [
            StageObservation(
                "profile_dataset",
                {
                    "retrieved_dataset_ids": ["abcd-1234"],
                    "attempted_dataset_ids": ["abcd-1234"],
                },
                {},
            )
        ],
        infrastructure_error="TimeoutError",
    )

    assert diagnostics["failure_stage"] == "profiling"
    assert diagnostics["failure_code"] == "harness_error"
    assert diagnostics["failure_owner"] == "infrastructure"


def test_diagnostics_approved_case_has_no_failure() -> None:
    final = {
        "status": "completed",
        "evidence": [{"dataset_id": "abcd-1234", "rows": []}],
        "claims": [],
        "usage": {"latency_ms": 12, "estimated_cost_usd": 0.001},
    }
    assessment = assess_case(_positive_case(), final)
    diagnostics = build_stage_diagnostics(_positive_case(), final, assessment)

    assert assessment.passed is True
    assert diagnostics["last_successful_stage"] == "acceptance"
    assert diagnostics["failure_stage"] is None
    assert diagnostics["failure_code"] is None


# --- T-617B0-R3: falla terminal de proveedor separada de la semántica -------
#
# Hallazgo del smoke real (eval run 9bebcb75-53d2-42f6-938f-bfbd45384128,
# agent run 235466d2-a403-4c01-bc8e-817713ca3062, pilot-005-empleo-publico):
# un 504 del proveedor durante `build_plan` persistió
# `agent_runs.status="failed"` + `terminal_error_code="LLM_PROVIDER_ERROR"`,
# pero `eval.run` nunca leía esos campos y `EvalCaseResult.error_code`
# quedaba en null. El diagnóstico degradaba a `intent_mismatch`/owner=agent:
# una falla de infraestructura se atribuía falsamente al agente.


@pytest.mark.parametrize(
    "provider_error_code,expected_failure_code",
    [
        ("LLM_PROVIDER_ERROR", "provider_error"),
        ("SOCRATA_TIMEOUT", "socrata_timeout"),
        ("SOCRATA_ERROR", "socrata_error"),
        ("RUN_TIMEOUT", "run_timeout"),
        ("HEARTBEAT_EXPIRED", "heartbeat_expired"),
        ("WORKER_LOST", "worker_lost"),
        ("INTERNAL", "internal_error"),
        # T-617B0-R3B: RUN_INTERRUPTED NO es cancelación del usuario — es el
        # arranque idempotente del backend marcando corridas con lease
        # vencida (plan.md §11, reinicio/despliegue); tan no evaluable como
        # HEARTBEAT_EXPIRED/WORKER_LOST.
        ("RUN_INTERRUPTED", "run_interrupted"),
    ],
)
def test_diagnostics_classifies_provider_terminal_error_as_infrastructure(
    provider_error_code: str, expected_failure_code: str
) -> None:
    """T-617B0-R3A: un terminal_error_code tipado de infraestructura/
    proveedor/ejecución nunca se clasifica como intent_mismatch, plan_invalid
    ni ningún otro código semántico: cada código tiene su propio
    failure_code inequívoco (INTERNAL no se disfraza de "proveedor"),
    siempre failure_owner=infrastructure, conservando la etapa observada
    donde ocurrió el fallo y la última etapa exitosa previa."""

    final = {"status": "failed", "evidence": [], "claims": [], "usage": {}}
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        final,
        assess_case(_positive_case(), final),
        [
            StageObservation("profile_dataset", {}, {}),
            StageObservation("build_plan", {}, {}),
        ],
        provider_error_code=provider_error_code,
    )

    assert diagnostics["failure_code"] == expected_failure_code
    assert diagnostics["failure_owner"] == "infrastructure"
    assert diagnostics["failure_stage"] == "planning"
    assert diagnostics["last_successful_stage"] == "profiling"
    assert diagnostics["terminal_error_code"] == provider_error_code
    assert diagnostics["failure_code"] != "intent_mismatch"
    assert diagnostics["failure_code"] != "plan_invalid"
    assert diagnostics["failure_code"] != "ambiguous_golden"


def test_diagnostics_structured_output_invalid_is_not_infrastructure() -> None:
    """T-617B0-R3A (hallazgo de auditoría #2): STRUCTURED_OUTPUT_INVALID NO es
    infraestructura/proveedor (contracts/api-rest.md §4: distingue
    explícitamente una salida que sigue sin cumplir el esquema tras agotar el
    repair loop de una falla real del proveedor). failure_owner="agent",
    failure_code="structured_output_invalid", y SIGUE contando como regresión
    semántica bloqueante si afecta un positivo sólido."""

    final = {"status": "failed", "evidence": [], "claims": [], "usage": {}}
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        final,
        assess_case(_positive_case(), final),
        [
            StageObservation("profile_dataset", {}, {}),
            StageObservation("build_plan", {}, {}),
        ],
        provider_error_code="STRUCTURED_OUTPUT_INVALID",
    )

    assert diagnostics["failure_code"] == "structured_output_invalid"
    assert diagnostics["failure_owner"] == "agent"
    assert diagnostics["failure_code"] != "provider_error"
    assert diagnostics["terminal_error_code"] == "STRUCTURED_OUTPUT_INVALID"


def test_diagnostics_unrecognized_terminal_error_code_does_not_force_infrastructure() -> None:
    """Un terminal_error_code presente pero fuera del mapeo de infraestructura
    y distinto de STRUCTURED_OUTPUT_INVALID (código verdaderamente
    desconocido para esta taxonomía) no fuerza ninguna clasificación
    especial: conserva el comportamiento previo por etapa/observaciones."""

    final = {"status": "eval_error", "evidence": [], "claims": [], "usage": {}}
    diagnostics = build_stage_diagnostics(
        _positive_case(),
        final,
        _failed_assessment(),
        [StageObservation("profile_dataset", {}, {})],
        provider_error_code="SOME_UNKNOWN_TERMINAL_CODE",
    )

    assert diagnostics["failure_code"] != "provider_error"
    assert diagnostics["failure_code"] != "structured_output_invalid"
    assert diagnostics["failure_owner"] != "infrastructure"
    assert diagnostics["terminal_error_code"] == "SOME_UNKNOWN_TERMINAL_CODE"


def test_diagnostics_provider_error_outranks_golden_ambiguous() -> None:
    """T-617B0-R3A (hallazgo de auditoría #4, requisito B): un caso con golden
    ambiguo (expected_facts sin expected_value) que ADEMÁS tiene un
    LLM_PROVIDER_ERROR terminal debe clasificarse como infraestructura, no
    como ambiguous_golden. Los fallos que impiden evaluar el caso tienen
    prioridad sobre la evaluación del golden."""

    ambiguous_case = _positive_case(expected_facts=({"description": "sin valor"},))
    final = {"status": "failed", "evidence": [], "claims": [], "usage": {}}
    diagnostics = build_stage_diagnostics(
        ambiguous_case,
        final,
        assess_case(ambiguous_case, final),
        [StageObservation("build_plan", {}, {})],
        provider_error_code="LLM_PROVIDER_ERROR",
    )

    assert diagnostics["failure_code"] == "provider_error"
    assert diagnostics["failure_owner"] == "infrastructure"
    assert diagnostics["failure_code"] != "ambiguous_golden"
    assert diagnostics["failure_owner"] != "golden"
