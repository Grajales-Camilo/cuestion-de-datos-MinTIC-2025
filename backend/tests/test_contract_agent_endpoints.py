"""Contrato T-304 (RF-201, RF-204, RF-801 y RF-803) sin red ni LLM real."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr


class DummySettings:
    sqlalchemy_database_url = "postgresql+psycopg://usuario:clave@localhost:5432/no_db"
    psycopg_database_url = "postgresql://usuario:clave@localhost:5432/no_db"
    max_concurrent_runs = 3
    retention_user_days = 90
    delete_active_grace_s = 0
    eval_mode = False
    retention_hash_salt = SecretStr("test-retention-hash-salt-32-bytes")


def _run(*, status: str = "running", expires_at: datetime | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        run_access_token_hash=("9" * 64),
        run_access_token_expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
        last_event_seq=3,
        steps_used=2,
        latency_ms=None,
        estimated_cost_usd=None,
        terminal_error_code="RUN_TIMEOUT" if status == "failed" else None,
        final_answer={
            "run_id": "placeholder",
            "status": status,
            "summary": None if status in {"failed", "interrupted"} else "Resultado",
            "narrative": None if status in {"failed", "interrupted"} else "Narrativa",
            "evidence": [],
            "claims": [],
            "no_evidence_report": None,
            "usage": {"steps_used": 2, "latency_ms": None, "estimated_cost_usd": None},
        },
    )


def _textual_fact() -> dict[str, object]:
    return {
        "fact_id": str(uuid.uuid4()),
        "fact_kind": "textual",
        "fact": "La ciudad es Medellín.",
        "operation": "direct_text",
        "evidence_id": str(uuid.uuid4()),
        "dataset_id": "abcd-1234",
        "source_row_indexes": [0],
        "columns": ["ciudad"],
        "raw_values": ["  Medellín  "],
        "normalized_values": ["medellín"],
        "display_value": "Medellín",
        "normalization_profile": "text-es-v1",
        "operation_params": {},
        "algorithm_version": "textual-fact-v1",
        "source_hash": f"sha256-jcs-v1:{'a' * 64}",
    }


def _client(monkeypatch, current_run):
    import app.main as main

    main.app.state.settings = DummySettings()
    main.app.state.worker_instance_id = "test-worker"
    main.app.state.run_creation_lock = None
    main.runner.ACTIVE_RUNS.clear()

    async def get_run(_database_url, _run_id):
        return current_run["value"]

    async def fetch_batch(_database_url, _run_id, _since_seq):
        return [], current_run["value"]

    async def get_detail(_database_url, _run_id):
        run = current_run["value"]
        return None if run is None else (run, [], [])

    async def delete_run(*_args, **_kwargs):
        current_run["value"] = None

    async def emit_started(*_args):
        return None

    monkeypatch.setattr(main, "_get_run_with_platform_loop", get_run)
    monkeypatch.setattr(main, "_fetch_stream_batch_with_platform_loop", fetch_batch)
    monkeypatch.setattr(main, "_get_run_detail_with_platform_loop", get_detail)
    monkeypatch.setattr(main, "_delete_run_with_platform_loop", delete_run)
    monkeypatch.setattr(main, "_emit_run_started_with_platform_loop", emit_started)
    return TestClient(main.app)


def test_query_rejects_short_question_and_public_retention_class(monkeypatch) -> None:
    current_run = {"value": _run()}
    client = _client(monkeypatch, current_run)

    short = client.post("/v2/agent/query", json={"question": "corta"})
    forced_retention = client.post(
        "/v2/agent/query",
        json={"question": "Pregunta publica suficientemente extensa", "retention_class": "eval"},
    )

    assert short.status_code == 422
    assert short.json()["error"]["code"] == "VALIDATION_ERROR"
    assert forced_retention.status_code == 422
    assert forced_retention.json()["error"]["code"] == "VALIDATION_ERROR"


def test_query_returns_token_once_and_applies_global_limit(monkeypatch) -> None:
    import app.main as main

    current_run = {"value": _run()}
    client = _client(monkeypatch, current_run)
    created_run = uuid.uuid4()
    captured = {}

    async def create_public(*_args, **kwargs):
        captured.update(kwargs)
        return created_run, "cdt_rt_only_once", datetime.now(UTC) + timedelta(days=90)

    def start_task(_settings, run_id):
        captured["started"] = run_id

    monkeypatch.setattr(main, "_create_public_run_with_platform_loop", create_public)
    monkeypatch.setattr(main.runner, "start_run_task", start_task)

    response = client.post(
        "/v2/agent/query",
        json={
            "question": "Pregunta publica suficientemente extensa",
            "options": {"llm_provider": "anthropic", "llm_model": "no-se-aplica"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["run_access_token"] == "cdt_rt_only_once"
    assert captured["started"] == created_run
    assert captured["context_hint"] is None

    main.runner.ACTIVE_RUNS.update({uuid.uuid4(): object() for _ in range(3)})
    limited = client.post("/v2/agent/query", json={"question": "Otra pregunta publica extensa"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_bearer_required_invalid_and_expired_runs_are_not_found(monkeypatch) -> None:
    import hashlib

    current_run = {"value": _run()}
    token = "cdt_rt_correcto"
    current_run["value"].run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    client = _client(monkeypatch, current_run)
    path = f"/v2/agent/runs/{current_run['value'].id}"

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer incorrecto"}).status_code == 401
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200

    current_run["value"] = _run(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    expired = client.get(f"/v2/agent/runs/{current_run['value'].id}")
    assert expired.status_code == 404
    assert expired.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert current_run["value"] is None


def test_stream_reconnect_and_terminal_sequence(monkeypatch) -> None:
    import hashlib

    import app.main as main

    token = "cdt_rt_stream"
    run = _run(status="completed")
    run.run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    current_run = {"value": run}
    client = _client(monkeypatch, current_run)
    events = [
        SimpleNamespace(seq=1, event_type="step", payload={"step_number": 1}),
        SimpleNamespace(seq=2, event_type="evidence", payload={"dataset_id": "abcd-1234"}),
        SimpleNamespace(seq=3, event_type="answer", payload=run.final_answer),
    ]

    async def fetch_batch(_database_url, _run_id, since_seq):
        return [event for event in events if event.seq > since_seq], run

    monkeypatch.setattr(main, "_fetch_stream_batch_with_platform_loop", fetch_batch)
    response = client.get(
        f"/v2/agent/stream/{run.id}",
        headers={"Authorization": f"Bearer {token}", "Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    assert "id: 2\nevent: evidence" in response.text
    assert "id: 3\nevent: answer" in response.text
    assert "id: 1" not in response.text
    assert response.text.count("event: answer") == 1
    assert '"textual_facts": []' in response.text
    assert '"partial_textual_facts": []' in response.text


def test_get_all_five_states_and_delete_is_idempotent(monkeypatch) -> None:
    import hashlib

    statuses = ["running", "completed", "no_evidence", "interrupted", "failed"]
    for state in statuses:
        token = f"cdt_rt_{state}"
        current_run = {"value": _run(status=state)}
        current_run["value"].run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
        client = _client(monkeypatch, current_run)
        path = f"/v2/agent/runs/{current_run['value'].id}"
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["status"] == state
        if state == "running":
            assert "answer" not in response.json()
        else:
            assert response.json()["answer"]["status"] == state
            assert response.json()["textual_facts"] == []
            assert response.json()["partial_textual_facts"] == []
            assert response.json()["answer"]["textual_facts"] == []
            assert response.json()["answer"]["partial_textual_facts"] == []

    token = "cdt_rt_delete"
    current_run = {"value": _run()}
    current_run["value"].run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    client = _client(monkeypatch, current_run)
    path = f"/v2/agent/runs/{current_run['value'].id}"
    first = client.delete(path, headers={"Authorization": f"Bearer {token}"})
    second = client.delete(path, headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 204
    assert second.status_code == 404


def test_textual_terminal_is_identical_in_rest_and_sse_replay(monkeypatch) -> None:
    import hashlib
    import json

    import app.main as main

    token = "cdt_rt_textual"
    run = _run(status="completed")
    run.run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    run.final_answer.update(
        {
            "summary": "Se encontraron hechos textuales verificables.",
            "narrative": "La ciudad es Medellín.",
            "textual_facts": [_textual_fact()],
            "partial_textual_facts": [],
        }
    )
    terminal = SimpleNamespace(seq=3, event_type="answer", payload=run.final_answer)
    current_run = {"value": run}
    client = _client(monkeypatch, current_run)

    async def fetch_batch(_database_url, _run_id, since_seq):
        return [terminal] if since_seq < 3 else [], run

    monkeypatch.setattr(main, "_fetch_stream_batch_with_platform_loop", fetch_batch)
    headers = {"Authorization": f"Bearer {token}"}
    rest = client.get(f"/v2/agent/runs/{run.id}", headers=headers)
    stream = client.get(
        f"/v2/agent/stream/{run.id}",
        headers={**headers, "Last-Event-ID": "2"},
    )

    assert rest.status_code == 200
    assert len(rest.json()["textual_facts"]) == 1
    assert rest.json()["textual_facts"][0]["display_value"] == "Medellín"
    assert rest.json()["answer"]["narrative"] == "La ciudad es Medellín."
    data_line = next(line for line in stream.text.splitlines() if line.startswith("data: "))
    replay_payload = json.loads(data_line.removeprefix("data: "))
    assert replay_payload == rest.json()["answer"]
    assert replay_payload["narrative"] == "La ciudad es Medellín."


def test_delete_without_retention_hash_salt_fails_clearly(monkeypatch) -> None:
    """research.md §4/data-model.md §7: sin `RETENTION_HASH_SALT` no hay forma
    segura de copiar métricas antes de borrar; debe fallar claro, no en silencio."""

    import hashlib

    import app.main as main

    token = "cdt_rt_missing_salt"
    current_run = {"value": _run()}
    current_run["value"].run_access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    client = _client(monkeypatch, current_run)
    main.app.state.settings.retention_hash_salt = None

    response = client.delete(
        f"/v2/agent/runs/{current_run['value'].id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL"
