"""T-304 contra PostgreSQL real: token, stream persistido y borrado completo."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.durability import get_run, reserve_and_emit_event, write_terminal_event_once
from app.agent.persistence import persist_final_answer
from app.agent.runner import create_public_run
from app.config import normalize_database_url_for_sqlalchemy

RETENTION_HASH_SALT = "test-retention-hash-salt-32-bytes-integration"

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_t304_real_postgres_stream_status_and_delete() -> None:
    """Una corrida real avanza, se reanuda por SSE y desaparece tras DELETE."""

    import app.main as main

    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    run_id: uuid.UUID | None = None
    created_run_id: uuid.UUID | None = None
    try:
        run_id, token, expires_at = await create_public_run(
            engine,
            worker_instance_id=None,  # type: ignore[arg-type] - FK nullable durante esta prueba HTTP.
            question="integracion real de endpoints T-304",
            context_hint="Prueba de integracion PostgreSQL real",
            retention_user_days=1,
        )
        created_run_id = run_id
        persisted_run = await get_run(engine, run_id)
        assert persisted_run is not None
        assert persisted_run.retention_class == "user"
        assert persisted_run.run_access_token_hash != token
        assert expires_at - persisted_run.created_at == timedelta(days=1)
        await reserve_and_emit_event(
            engine,
            run_id,
            "step",
            {
                "step_number": 1,
                "node": "planner",
                "display_message": "Preparando la investigacion.",
                "detail": {},
            },
        )
        answer = {
            "run_id": str(run_id),
            "status": "completed",
            "intention": "Prueba de stream durable",
            "summary": "Resultado de prueba sin cifras.",
            "narrative": "La corrida de prueba persistio sus eventos.",
            "evidence": [],
            "claims": [],
            "no_evidence_report": None,
            "usage": {"steps_used": 1, "latency_ms": 10, "estimated_cost_usd": 0},
        }
        await persist_final_answer(
            engine,
            run_id,
            answer,
            latency_ms=10,
            llm_provider="google",
            llm_model="scripted-test",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
        )
        await write_terminal_event_once(
            engine, run_id, status="completed", error_code=None, payload=answer
        )

        main.app.state.settings = SimpleNamespace(
            sqlalchemy_database_url=normalize_database_url_for_sqlalchemy(
                os.environ["DATABASE_URL"]
            ),
            psycopg_database_url=os.environ["DATABASE_URL"],
            delete_active_grace_s=0,
            retention_hash_salt=SecretStr(RETENTION_HASH_SALT),
        )
        headers = {"Authorization": f"Bearer {token}"}
        client = TestClient(main.app)

        stream = client.get(f"/v2/agent/stream/{run_id}", headers={**headers, "Last-Event-ID": "1"})
        assert stream.status_code == 200
        assert "id: 2\nevent: answer" in stream.text
        assert "id: 1" not in stream.text
        assert '"textual_facts": []' in stream.text
        assert '"partial_textual_facts": []' in stream.text

        status_response = client.get(f"/v2/agent/runs/{run_id}", headers=headers)
        assert status_response.status_code == 200
        assert status_response.json()["answer"]["status"] == "completed"
        assert status_response.json()["textual_facts"] == []
        assert status_response.json()["partial_textual_facts"] == []

        deleted = client.delete(f"/v2/agent/runs/{run_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(f"/v2/agent/runs/{run_id}", headers=headers).status_code == 404

        source_run_hash = hashlib.sha256(f"{run_id}{RETENTION_HASH_SALT}".encode()).hexdigest()
        async with engine.begin() as connection:
            metric_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT retention_class_origin, status_final, llm_provider, llm_model, "
                            "steps_used, latency_ms, estimated_cost_usd, deletion_reason "
                            "FROM technical_metrics WHERE source_run_hash = :hash"
                        ),
                        {"hash": source_run_hash},
                    )
                )
                .mappings()
                .one()
            )
        assert metric_row["retention_class_origin"] == "user"
        assert metric_row["status_final"] == "completed"
        assert metric_row["llm_provider"] == "google"
        assert metric_row["llm_model"] == "scripted-test"
        assert metric_row["latency_ms"] == 10
        assert metric_row["deletion_reason"] == "user_requested"
        run_id = None
    finally:
        if run_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM agent_runs WHERE id = :id"), {"id": run_id}
                )
        if created_run_id is not None:
            cleanup_hash = hashlib.sha256(
                f"{created_run_id}{RETENTION_HASH_SALT}".encode()
            ).hexdigest()
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM technical_metrics WHERE source_run_hash = :hash"),
                    {"hash": cleanup_hash},
                )
        await engine.dispose()
