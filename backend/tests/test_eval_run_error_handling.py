"""Un caso que falla no debe tumbar los otros 49 ni dejar la corrida sin cerrar."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


async def test_run_suite_persists_a_failed_case_and_still_finalizes(monkeypatch) -> None:
    suite = _fake_suite()
    suite_id = uuid.uuid4()
    case_ids = {case.case_id: uuid.uuid4() for case in suite.cases}

    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(run_module, "default_suite_path", lambda name: "irrelevant")
    monkeypatch.setattr(run_module, "load_golden_suite", lambda path: suite)
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

    persisted_calls = []

    async def fake_persist(engine, **kwargs):
        persisted_calls.append(kwargs)

    monkeypatch.setattr(run_module, "_persist_case_result", fake_persist)

    finalize_calls = []

    async def fake_finalize(engine, *, record_id, results):
        finalize_calls.append((record_id, results))

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
    assert "boom" in failed_call["assessment"].failure_reason

    ok_call = persisted_calls[1]
    assert ok_call["error_code"] is None
    assert ok_call["assessment"].passed is True

    # La corrida se cierra (finaliza) aunque un caso haya reventado.
    assert len(finalize_calls) == 1
    _, results = finalize_calls[0]
    assert len(results) == 2


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
                'insert or update on table "eval_case_results" violates '
                "foreign key constraint"
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
