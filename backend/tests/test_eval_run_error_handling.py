"""Un caso que falla no debe tumbar los otros 49 ni dejar la corrida sin cerrar."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import eval.run as run_module
from app.config import Settings
from eval.loader import GoldenCase, GoldenSuite
from eval.persistence import PersistedGoldenSuite


def _settings(**overrides: object) -> Settings:
    """`_env_file=None` aísla la prueba del `.env` local real (mismo hallazgo
    del agente evaluador que en `test_llm_factory.py::settings`)."""
    values = {
        "DATABASE_URL": "postgresql://usuario:clave@localhost:5432/cuestion_de_datos",
        "SOCRATA_APP_TOKEN": "token-local",
        "RETENTION_HASH_SALT": "replace-with-local-development-salt-32-bytes",
        "EVAL_MODE": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _fake_suite() -> GoldenSuite:
    cases = (
        GoldenCase("c1", "positive", "q1", ("abcd-1234",), (), 1, "n"),
        GoldenCase("c2", "positive", "q2", ("abcd-5678",), (), 2, "n"),
    )
    return GoldenSuite(
        name="golden-v1", version="1.0.0", snapshot_at="2026-07-11", cases=cases, source_path=None
    )


def test_config_snapshot_registers_deterministic_textual_facts_enabled(monkeypatch) -> None:
    """T-617B0-R3 #6: config_snapshot debe registrar
    deterministic_textual_facts_enabled porque afecta el contrato del
    planificador determinista y hoy no quedaba registrado en la corrida de
    evaluación."""

    monkeypatch.setattr(run_module, "_git_commit", lambda: "abc123")
    settings = _settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=True)

    snapshot = run_module._config_snapshot(settings, seed=601000)

    assert snapshot["deterministic_textual_facts_enabled"] is True
    assert snapshot["eval_seed"] == 601000


@pytest.mark.parametrize(
    "run_status,terminal_error_code,expected_failure_code",
    [
        ("failed", "LLM_PROVIDER_ERROR", "provider_error"),
        # T-617B0-R3A #5 (requisito D/E.5): HEARTBEAT_EXPIRED/WORKER_LOST se
        # persisten con status="interrupted" (app.agent.heartbeat_sweep), no
        # "failed". La solución adoptada (opción 1 de la auditoría) es leer
        # AMBOS estados no evaluables; sin esto, esta rama de la
        # parametrización fallaría con error_code=None.
        ("interrupted", "HEARTBEAT_EXPIRED", "heartbeat_expired"),
    ],
)
async def test_run_suite_propagates_provider_terminal_from_agent_run(
    monkeypatch, run_status: str, terminal_error_code: str, expected_failure_code: str
) -> None:
    """T-617B0-R3A #1 (prueba integral, requisito E.1): reproduce el punto
    originalmente defectuoso dentro de `run_suite` — no solo
    `build_stage_diagnostics`/`evaluate_smoke_gate` por separado. `get_run`
    devuelve un `status`/`terminal_error_code` no evaluable y
    `final_answer=None` (como el agent run real
    235466d2-a403-4c01-bc8e-817713ca3062 del smoke, para el caso
    `status="failed"`). Sin la lectura de
    `run.status`/`run.terminal_error_code` en `run_suite`, esta prueba falla
    contra e74f3522853c75f6ae6ad984048bc327669602bb con
    `error_code is None` y `failure_code == "intent_mismatch"`."""

    suite = GoldenSuite(
        name="golden-v1",
        version="1.0.0",
        snapshot_at="2026-07-11",
        cases=(
            GoldenCase("pilot-005-empleo-publico", "positive", "q1", ("abcd-1234",), (), 1, "n"),
        ),
        source_path=None,
    )
    suite_id = uuid.uuid4()
    case_ids = {case.case_id: uuid.uuid4() for case in suite.cases}

    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)
    monkeypatch.setattr(run_module, "validate_gate_selection", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "create_app_async_engine",
        lambda *a, **k: SimpleNamespace(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        run_module,
        "sync_golden_suite",
        AsyncMock(return_value=PersistedGoldenSuite(suite_id=suite_id, case_ids=case_ids)),
    )
    monkeypatch.setattr(run_module, "register_worker_instance", AsyncMock(return_value="worker-1"))
    monkeypatch.setattr(run_module, "mark_worker_shutdown", AsyncMock())
    monkeypatch.setattr(run_module, "create_eval_run", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(run_module, "execute_agent_run_async", AsyncMock())
    # No relanza excepción: el agente mismo capturó el 504 de proveedor y
    # persistió el terminal en `agent_runs`, sin `final_answer`.
    monkeypatch.setattr(
        run_module,
        "get_run",
        AsyncMock(
            return_value=SimpleNamespace(
                status=run_status,
                terminal_error_code=terminal_error_code,
                final_answer=None,
            )
        ),
    )
    monkeypatch.setattr(run_module, "_planner_search_dataset_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(run_module, "_stage_observations", AsyncMock(return_value=()))

    persisted_calls = []

    async def fake_persist(engine, **kwargs):
        persisted_calls.append(kwargs)

    monkeypatch.setattr(run_module, "_persist_case_result", fake_persist)
    monkeypatch.setattr(run_module, "_finalize_eval_record", AsyncMock())
    monkeypatch.setattr(run_module, "_write_report", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "_create_eval_record",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid.uuid4(), llm_provider="google", llm_model="gemini-2.5-flash"
            )
        ),
    )

    result = await run_module.run_suite(
        suite_name="golden-v1", provider=None, model=None, seed=1, limit=None
    )

    assert len(persisted_calls) == 1
    call = persisted_calls[0]
    assert call["error_code"] == terminal_error_code
    assert call["assessment"].passed is False
    assert call["stage_diagnostics"]["failure_code"] == expected_failure_code
    assert call["stage_diagnostics"]["failure_owner"] == "infrastructure"
    assert call["stage_diagnostics"]["terminal_error_code"] == terminal_error_code
    assert call["stage_diagnostics"]["failure_code"] != "intent_mismatch"

    assert result.aggregate is not None
    assert result.aggregate.infrastructure_failure_count == 1
    assert result.aggregate.infrastructure_failure_case_ids == ("pilot-005-empleo-publico",)

    assert result.verdict is not None
    assert result.verdict.passed is False
    infra_metric = next(m for m in result.verdict.metrics if m.name == "infraestructura")
    assert infra_metric.passed is False
    assert any("infraestructura" in reason for reason in result.verdict.blocking_reasons)


async def test_run_suite_persists_a_failed_case_and_still_finalizes(monkeypatch) -> None:
    suite = _fake_suite()
    suite_id = uuid.uuid4()
    case_ids = {case.case_id: uuid.uuid4() for case in suite.cases}

    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)
    # Esta prueba aísla la resiliencia del bucle por-caso, no la puerta: el
    # preflight de selección (validate_gate_selection) se cubre en sus propias
    # pruebas dedicadas y aquí se neutraliza como un colaborador más, igual que
    # engine/sync/register, para conservar el mini-suite de 2 casos.
    monkeypatch.setattr(run_module, "validate_gate_selection", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "create_app_async_engine",
        lambda *a, **k: SimpleNamespace(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        run_module,
        "sync_golden_suite",
        AsyncMock(return_value=PersistedGoldenSuite(suite_id=suite_id, case_ids=case_ids)),
    )
    monkeypatch.setattr(run_module, "register_worker_instance", AsyncMock(return_value="worker-1"))
    monkeypatch.setattr(run_module, "mark_worker_shutdown", AsyncMock())

    # El primer caso revienta (p. ej. timeout de LLM); el segundo corre limpio.
    monkeypatch.setattr(
        run_module,
        "create_eval_run",
        AsyncMock(side_effect=[RuntimeError("boom"), uuid.uuid4()]),
    )
    monkeypatch.setattr(run_module, "execute_agent_run_async", AsyncMock())
    monkeypatch.setattr(
        run_module,
        "get_run",
        AsyncMock(
            return_value=SimpleNamespace(
                final_answer={
                    "status": "completed",
                    "evidence": [{"dataset_id": "abcd-5678", "rows": []}],
                    "claims": [],
                }
            )
        ),
    )
    monkeypatch.setattr(run_module, "_planner_search_dataset_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(run_module, "_stage_observations", AsyncMock(return_value=()))

    persisted_calls = []

    async def fake_persist(engine, **kwargs):
        persisted_calls.append(kwargs)

    monkeypatch.setattr(run_module, "_persist_case_result", fake_persist)

    finalize_calls = []

    async def fake_finalize(engine, *, record_id, aggregate):
        finalize_calls.append((record_id, aggregate))

    monkeypatch.setattr(run_module, "_finalize_eval_record", fake_finalize)
    monkeypatch.setattr(run_module, "_write_report", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "_create_eval_record",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid.uuid4(), llm_provider="google", llm_model="gemini-2.5-flash"
            )
        ),
    )

    result = await run_module.run_suite(
        suite_name="golden-v1", provider=None, model=None, seed=1, limit=None
    )

    assert result.report_path is not None
    # Los dos casos se persistieron: el que reventó y el que corrió limpio.
    assert len(persisted_calls) == 2
    failed_call = persisted_calls[0]
    assert failed_call["agent_run_id"] is None
    assert failed_call["error_code"] == "RuntimeError"
    assert failed_call["assessment"].passed is False
    # T-617B0-R3A: una excepción del arnés (runner/engine/persistencia/
    # dependencia del evaluador, aquí `create_eval_run` reventando) bloquea
    # como infraestructura, NUNCA como regresión semántica del agente.
    assert failed_call["stage_diagnostics"]["failure_code"] == "harness_error"
    assert failed_call["stage_diagnostics"]["failure_owner"] == "infrastructure"
    assert "boom" in failed_call["assessment"].failure_reason

    ok_call = persisted_calls[1]
    assert ok_call["error_code"] is None
    assert ok_call["assessment"].passed is True

    # La corrida se cierra (finaliza) aunque un caso haya reventado.
    assert len(finalize_calls) == 1
    _, aggregate = finalize_calls[0]
    # Ambos casos son positivos: uno reventó, el otro pasó => 1/2 sobre positivos.
    assert aggregate.positive_total == 2
    assert aggregate.positive_passed == 1
    assert aggregate.success_rate == 0.5


async def test_run_suite_retries_persistence_without_agent_run_id_and_keeps_going(
    monkeypatch,
) -> None:
    """Si agent_run_id desaparece entre la ejecucion y la persistencia (p. ej. un
    barrido de retencion concurrente viola la FK), el caso no debe tumbar el resto
    de la corrida: se reintenta sin la referencia rota."""

    suite = _fake_suite()
    suite_id = uuid.uuid4()
    case_ids = {case.case_id: uuid.uuid4() for case in suite.cases}

    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)
    # Igual que la prueba anterior: se aísla la resiliencia del bucle, no la
    # puerta; el preflight se neutraliza para conservar el mini-suite de 2 casos.
    monkeypatch.setattr(run_module, "validate_gate_selection", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "create_app_async_engine",
        lambda *a, **k: SimpleNamespace(dispose=AsyncMock()),
    )
    monkeypatch.setattr(
        run_module,
        "sync_golden_suite",
        AsyncMock(return_value=PersistedGoldenSuite(suite_id=suite_id, case_ids=case_ids)),
    )
    monkeypatch.setattr(run_module, "register_worker_instance", AsyncMock(return_value="worker-1"))
    monkeypatch.setattr(run_module, "mark_worker_shutdown", AsyncMock())
    monkeypatch.setattr(run_module, "create_eval_run", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(run_module, "execute_agent_run_async", AsyncMock())
    monkeypatch.setattr(
        run_module,
        "get_run",
        AsyncMock(
            return_value=SimpleNamespace(
                final_answer={"status": "no_evidence", "evidence": [], "claims": []}
            )
        ),
    )
    monkeypatch.setattr(run_module, "_planner_search_dataset_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(run_module, "_stage_observations", AsyncMock(return_value=()))
    monkeypatch.setattr(
        run_module,
        "_create_eval_record",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid.uuid4(), llm_provider="google", llm_model="gemini-2.5-flash"
            )
        ),
    )
    monkeypatch.setattr(run_module, "_finalize_eval_record", AsyncMock())
    monkeypatch.setattr(run_module, "_write_report", lambda *a, **k: None)

    persisted_calls = []

    async def flaky_persist(engine, **kwargs):
        persisted_calls.append(kwargs)
        # Solo la primera llamada (caso 1, con agent_run_id valido) falla.
        if len(persisted_calls) == 1:
            raise RuntimeError(
                'insert or update on table "eval_case_results" violates foreign key constraint'
            )

    monkeypatch.setattr(run_module, "_persist_case_result", flaky_persist)

    result = await run_module.run_suite(
        suite_name="golden-v1", provider=None, model=None, seed=1, limit=None
    )

    assert result.report_path is not None
    # caso1 intento fallido + caso1 reintento + caso2 sin problema = 3 llamadas.
    assert len(persisted_calls) == 3
    assert persisted_calls[0]["agent_run_id"] is not None
    assert persisted_calls[1]["agent_run_id"] is None
    assert persisted_calls[1]["error_code"] == "RuntimeError"
    assert persisted_calls[2]["agent_run_id"] is not None


@pytest.mark.parametrize(
    "gate_mode,match",
    [("full", "puerta full"), ("smoke", "puerta smoke")],
)
async def test_run_suite_preflight_rejects_incompatible_selection_before_engine(
    monkeypatch, gate_mode: str, match: str
) -> None:
    """T-617B0-R2: el preflight rechaza una selección incompatible con la puerta
    ANTES de crear el engine o invocar el agente/LLM. `_fake_suite` tiene solo 2
    positivos: ni completa la puerta full (50 casos) ni cubre los 10 canónicos
    del smoke. Espías demuestran que no se gastó cuota."""

    suite = _fake_suite()
    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)

    engine_calls: list[object] = []

    def spy_engine(*a, **k):
        engine_calls.append((a, k))
        return SimpleNamespace(dispose=AsyncMock())

    monkeypatch.setattr(run_module, "create_app_async_engine", spy_engine)

    llm_calls: list[int] = []
    monkeypatch.setattr(
        run_module,
        "create_eval_run",
        AsyncMock(side_effect=lambda *a, **k: llm_calls.append(1)),
    )
    monkeypatch.setattr(
        run_module,
        "execute_agent_run_async",
        AsyncMock(side_effect=lambda *a, **k: llm_calls.append(1)),
    )
    # Otros colaboradores de I/O: si el preflight fallara en abortar, estos
    # revelarían la fuga; deben quedar intactos (nunca invocados).
    sync_spy = AsyncMock()
    monkeypatch.setattr(run_module, "sync_golden_suite", sync_spy)
    register_spy = AsyncMock(return_value="worker-1")
    monkeypatch.setattr(run_module, "register_worker_instance", register_spy)

    with pytest.raises(RuntimeError, match=match):
        await run_module.run_suite(
            suite_name="golden-v1",
            provider=None,
            model=None,
            seed=1,
            limit=None,
            gate_mode=gate_mode,
        )

    assert engine_calls == []  # engine nunca creado
    assert llm_calls == []  # agente/LLM nunca invocado
    sync_spy.assert_not_awaited()
    register_spy.assert_not_awaited()


async def test_run_suite_preflight_rejects_unknown_gate_mode_before_engine(monkeypatch) -> None:
    """Un gate_mode programático desconocido se rechaza explícitamente antes de
    tocar el engine (defensa contra invocaciones internas mal formadas)."""

    suite = _fake_suite()
    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)

    engine_calls: list[object] = []
    monkeypatch.setattr(
        run_module,
        "create_app_async_engine",
        lambda *a, **k: engine_calls.append((a, k)) or SimpleNamespace(dispose=AsyncMock()),
    )

    with pytest.raises(RuntimeError, match="gate_mode desconocido"):
        await run_module.run_suite(
            suite_name="golden-v1",
            provider=None,
            model=None,
            seed=1,
            limit=None,
            gate_mode="bogus",
        )

    assert engine_calls == []


def test_select_cases_supports_exact_generic_case_ids() -> None:
    suite = _fake_suite()

    selected = run_module._select_cases(
        suite.cases,
        limit=None,
        case_ids=[suite.cases[1].case_id],
    )

    assert selected == [suite.cases[1]]


def test_select_cases_rejects_unknown_case_id() -> None:
    suite = _fake_suite()

    with pytest.raises(RuntimeError, match="case_id inexistente: missing"):
        run_module._select_cases(suite.cases, limit=None, case_ids=["missing"])


def test_report_renders_stage_reason_and_retrieval_tables(tmp_path: Path) -> None:
    assessment = run_module.CaseAssessment(False, False, False, (), (), "sin dataset")
    diagnostics = {
        "agent_run_id": "run-1",
        "last_successful_stage": None,
        "failure_stage": "retrieval",
        "failure_code": "expected_dataset_not_retrieved",
        "failure_owner": "agent",
        "retrieved_dataset_ids": ["other-id"],
        "attempted_dataset_ids": [],
        "accepted_dataset_id": None,
        "expected_dataset_rank": None,
        "candidate_count": 1,
        "query_count": 0,
        "exploration_count": 0,
        "llm_call_count": 1,
        "stop_reason": None,
        "evidence_count": 0,
        "claim_count": 0,
        "facts_verified": False,
        "latency_ms": 10,
        "estimated_cost_usd": 0,
    }
    target = tmp_path / "report.md"

    case = GoldenCase("case-1", "positive", "q", ("abcd-1234",), (), 1, "n")
    outcome = run_module._build_case_outcome(
        case,
        assessment,
        diagnostics,
        run_module.evaluate_claims_integrity({"status": "no_evidence"}),
        (),
    )
    aggregate = run_module.aggregate_metrics([outcome])
    verdict = run_module.evaluate_full_gate(aggregate)

    run_module._write_report(
        target,
        record=SimpleNamespace(
            id="eval-1",
            llm_provider="google",
            llm_model="model",
            embedding_model="embedding-model",
            eval_seed=614010,
            git_commit="abc123",
            config_snapshot={"runtime": "deterministic"},
        ),
        suite_name="golden-v2",
        results=[("case-1", assessment, diagnostics)],
        aggregate=aggregate,
        verdict=verdict,
    )

    report = target.read_text(encoding="utf-8")
    assert "- Suite: golden-v2" in report
    assert "## Fallos por etapa" in report
    assert "expected_dataset_not_retrieved" in report
    assert "## Recuperación" in report
    assert "other-id" in report
    assert "## Veredicto de puerta" in report
    assert "Positivos aprobados: 0/1" in report
