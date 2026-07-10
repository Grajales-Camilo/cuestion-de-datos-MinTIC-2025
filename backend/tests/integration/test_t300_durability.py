"""Integracion T-300: durabilidad real de corridas (plan.md §11).

Concurrencia real via `asyncio.gather` con conexiones/sesiones independientes
sobre el mismo `run_id` -- nunca awaits secuenciales disfrazados de
concurrencia -- y una demo que mata el proceso de verdad
(`subprocess.Popen(...).kill()`, `TerminateProcess` en Windows, NO un
shutdown limpio) para cubrir el criterio de aceptacion literal de T-300.
"""

import asyncio
import contextlib
import os
import socket
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import durability, heartbeat_sweep, worker_lease
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import AgentRun, WorkerInstance

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
PYTHON_EXE = str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe")
LEASE_TTL_S = 30  # piso normativo de config.py: WORKER_LEASE_TTL_S >= 30


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=20, max_overflow=20)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_agent_tables(engine):
    async def _clean() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM agent_run_events"))
            await connection.execute(text("DELETE FROM agent_runs"))
            await connection.execute(text("DELETE FROM worker_instances"))

    await _clean()
    yield
    await _clean()


async def _insert_worker(
    engine, *, lease_expires_at: datetime, heartbeat_at: datetime | None = None
) -> str:
    worker_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            WorkerInstance(
                id=worker_id,
                started_at=now,
                heartbeat_at=heartbeat_at or now,
                lease_expires_at=lease_expires_at,
                status="active",
            )
        )
    return worker_id


async def _insert_run(
    engine,
    *,
    worker_instance_id: str,
    heartbeat_at: datetime | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question="prueba de integracion T-300",
                status="running",
                worker_instance_id=worker_instance_id,
                heartbeat_at=heartbeat_at or now,
                last_event_seq=0,
                run_access_token_hash="x" * 16,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class="user",
                created_at=created_at or now,
            )
        )
    return run_id


# --- 1. Dos emisores concurrentes serializan sin duplicar seq --------------


async def test_concurrent_emitters_produce_contiguous_seq_without_duplicates(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(engine, worker_instance_id=worker_id)

    concurrency = 12
    results = await asyncio.gather(
        *[
            durability.reserve_and_emit_event(engine, run_id, "step", {"i": i})
            for i in range(concurrency)
        ]
    )

    seqs = sorted(event.seq for event in results)
    assert seqs == list(range(1, concurrency + 1)), "secuencia no contigua o con duplicados"

    stored = await durability.list_events_since(engine, run_id, 0)
    assert [e.seq for e in stored] == list(range(1, concurrency + 1))


# --- 2. Timeout compitiendo con un evento normal ----------------------------


async def test_timeout_racing_with_normal_terminal_event_writes_at_most_one(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(engine, worker_instance_id=worker_id)

    results = await asyncio.gather(
        durability.write_terminal_event_once(
            engine, run_id, status="failed", error_code="RUN_TIMEOUT", payload={"race": "timeout"}
        ),
        durability.write_terminal_event_once(
            engine, run_id, status="completed", error_code=None, payload={"race": "answer"}
        ),
    )

    winners = [r for r in results if r is not None]
    assert len(winners) == 1, "debe ganar exactamente una transicion terminal"

    events = await durability.list_events_since(engine, run_id, 0)
    terminal_events = [e for e in events if e.event_type in ("answer", "error")]
    assert len(terminal_events) == 1


# --- 3. Detector de worker perdido ------------------------------------------


async def test_worker_lost_detected_by_periodic_sweep(engine) -> None:
    dead_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) - timedelta(seconds=5)
    )
    run_id = await _insert_run(engine, worker_instance_id=dead_worker_id)
    own_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    summary = await heartbeat_sweep.sweep_orphaned_runs(
        engine, own_worker_instance_id=own_worker_id, heartbeat_timeout_s=120, max_duration_s=600
    )
    assert run_id in summary.worker_lost

    run = await durability.get_run(engine, run_id)
    assert run.status == "interrupted"
    assert run.terminal_error_code == "WORKER_LOST"

    # Repetir el barrido no duplica el evento terminal (ya no es "running").
    summary_again = await heartbeat_sweep.sweep_orphaned_runs(
        engine, own_worker_instance_id=own_worker_id, heartbeat_timeout_s=120, max_duration_s=600
    )
    assert run_id not in summary_again.worker_lost

    events = await durability.list_events_since(engine, run_id, 0)
    assert len([e for e in events if e.event_type == "error"]) == 1


# --- 4. Escritura duplicada del evento terminal (idempotencia) -------------


async def test_write_terminal_event_once_is_idempotent_on_retry(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(engine, worker_instance_id=worker_id)

    first = await durability.write_terminal_event_once(
        engine, run_id, status="completed", error_code=None, payload={"try": 1}
    )
    second = await durability.write_terminal_event_once(
        engine, run_id, status="failed", error_code="INTERNAL", payload={"try": 2}
    )

    assert first is not None
    assert second is None

    events = await durability.list_events_since(engine, run_id, 0)
    assert len(events) == 1
    assert events[0].payload == {"try": 1}


# --- 5. Rollback tras reservar seq no deja hueco observable -----------------


async def test_rollback_after_reserving_seq_reuses_number_without_gap(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(engine, worker_instance_id=worker_id)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    try:
        await session.begin()
        reserved = (
            await session.execute(
                text(
                    "UPDATE agent_runs SET last_event_seq = last_event_seq + 1 "
                    "WHERE id = :run_id RETURNING last_event_seq"
                ),
                {"run_id": run_id},
            )
        ).scalar_one()
        assert reserved == 1
        await session.rollback()  # no se inserta el evento: el incremento revierte
    finally:
        await session.close()

    emitted = await durability.reserve_and_emit_event(engine, run_id, "step", {"real": True})

    assert emitted.seq == 1, "el numero reservado y revertido debe poder reutilizarse"
    events = await durability.list_events_since(engine, run_id, 0)
    assert [e.seq for e in events] == [1]


# --- 6. Reintento idempotente de reconexion (sin duplicar ni perder) -------


async def test_list_events_since_supports_repeated_reconnection_without_loss(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(engine, worker_instance_id=worker_id)

    for i in range(5):
        await durability.reserve_and_emit_event(engine, run_id, "step", {"i": i})

    assert [e.seq for e in await durability.list_events_since(engine, run_id, 0)] == [1, 2, 3, 4, 5]
    assert [e.seq for e in await durability.list_events_since(engine, run_id, 3)] == [4, 5]
    # Reconectar de nuevo con el mismo Last-Event-ID: mismos eventos, sin duplicar.
    assert [e.seq for e in await durability.list_events_since(engine, run_id, 3)] == [4, 5]


# --- 7. Nueva instancia NO interrumpe corridas con lease vigente ------------


async def test_new_instance_does_not_interrupt_run_with_valid_lease(engine) -> None:
    alive_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)
    )
    run_id = await _insert_run(engine, worker_instance_id=alive_worker_id)
    new_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    closed = await worker_lease.close_stale_running_runs(engine, new_worker_id)

    assert closed == 0
    run = await durability.get_run(engine, run_id)
    assert run.status == "running"
    assert run.terminal_error_code is None


# --- 8. Arranque idempotente no duplica el evento terminal -----------------


async def test_startup_idempotent_close_does_not_duplicate_terminal_event(engine) -> None:
    dead_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) - timedelta(minutes=5)
    )
    run_id = await _insert_run(engine, worker_instance_id=dead_worker_id)
    new_worker_id = await _insert_worker(
        engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    closed_first = await worker_lease.close_stale_running_runs(engine, new_worker_id)
    closed_second = await worker_lease.close_stale_running_runs(engine, new_worker_id)

    assert closed_first == 1
    assert closed_second == 0

    run = await durability.get_run(engine, run_id)
    assert run.status == "interrupted"
    assert run.terminal_error_code == "RUN_INTERRUPTED"

    events = await durability.list_events_since(engine, run_id, 0)
    assert len([e for e in events if e.event_type == "error"]) == 1


# --- 9. Duracion maxima excedida => failed/RUN_TIMEOUT (nunca interrupted) -


async def test_max_duration_exceeded_transitions_to_failed_run_timeout(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(
        engine,
        worker_instance_id=worker_id,
        created_at=datetime.now(UTC) - timedelta(seconds=700),
    )

    summary = await heartbeat_sweep.sweep_orphaned_runs(
        engine, own_worker_instance_id=worker_id, heartbeat_timeout_s=120, max_duration_s=600
    )

    assert run_id in summary.timed_out
    run = await durability.get_run(engine, run_id)
    assert run.status == "failed"
    assert run.terminal_error_code == "RUN_TIMEOUT"


async def test_heartbeat_expired_transitions_to_interrupted(engine) -> None:
    worker_id = await _insert_worker(engine, lease_expires_at=datetime.now(UTC) + timedelta(days=1))
    run_id = await _insert_run(
        engine,
        worker_instance_id=worker_id,
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=200),
    )

    summary = await heartbeat_sweep.sweep_orphaned_runs(
        engine, own_worker_instance_id=worker_id, heartbeat_timeout_s=120, max_duration_s=600
    )

    assert run_id in summary.heartbeat_expired
    run = await durability.get_run(engine, run_id)
    assert run.status == "interrupted"
    assert run.terminal_error_code == "HEARTBEAT_EXPIRED"


# --- 10. Demo real de matar el proceso (criterio de aceptacion de T-300) ---


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(port: int, extra_env: dict[str, str]) -> subprocess.Popen:
    env = {**os.environ, **extra_env}
    proc = subprocess.Popen(
        [PYTHON_EXE, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/v2/health", timeout=1)
            if response.status_code in (200, 503):
                return proc
        except httpx.TransportError:
            pass
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError("el servidor de prueba no arranco a tiempo")


def test_real_process_kill_demo_interrupts_and_reconnects_without_loss() -> None:
    """Criterio de aceptacion literal de T-300: iniciar corrida, recibir 2+
    eventos, matar el proceso DE VERDAD (`Popen.kill()` = `TerminateProcess`
    en Windows, no un shutdown limpio -- research.md §2), reiniciar,
    reconectar con `Last-Event-ID` y recibir los eventos faltantes + un
    estado terminal `interrupted/RUN_INTERRUPTED` coherente, sin perdida ni
    duplicacion."""

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {"RUN_HEARTBEAT_TIMEOUT_S": "30", "WORKER_LEASE_TTL_S": "30"}

    proc1 = _start_server(port, env)
    proc2: subprocess.Popen | None = None
    try:
        response = httpx.post(f"{base_url}/v2/_poc/agent/query", json={"step_delay_s": 2.0})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        last_seq = 0
        events_seen = 0
        with httpx.stream("GET", f"{base_url}/v2/_poc/agent/stream/{run_id}", timeout=30) as resp:
            for line in resp.iter_lines():
                if line.startswith("id:"):
                    last_seq = int(line.split(":", 1)[1].strip())
                    events_seen += 1
                if events_seen >= 2:
                    break
        assert events_seen >= 2, "se esperaban 2+ eventos antes de matar el proceso"

        proc1.kill()  # TerminateProcess real; NO un shutdown limpio
        proc1.wait(timeout=10)
        assert proc1.returncode != 0

        with pytest.raises(httpx.TransportError):
            httpx.get(f"{base_url}/v2/health", timeout=1)

        # Piso normativo config.py: WORKER_LEASE_TTL_S >= 30. Se espera a que
        # la lease de la instancia muerta venza de verdad antes de reiniciar.
        time.sleep(LEASE_TTL_S + 3)

        proc2 = _start_server(port, env)

        pending_seq: int | None = None
        final_events: list[tuple[int, str]] = []
        with httpx.stream(
            "GET",
            f"{base_url}/v2/_poc/agent/stream/{run_id}",
            headers={"Last-Event-ID": str(last_seq)},
            timeout=15,
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("id:"):
                    pending_seq = int(line.split(":", 1)[1].strip())
                elif line.startswith("event:") and pending_seq is not None:
                    final_events.append((pending_seq, line.split(":", 1)[1].strip()))
                    pending_seq = None

        assert final_events, "se esperaban eventos faltantes tras reconectar"
        seqs = [seq for seq, _ in final_events]
        assert seqs == sorted(set(seqs)), "secuencia con huecos o duplicados"
        assert seqs[0] == last_seq + 1, "no debe perder ni repetir eventos ya vistos"

        _, last_event_type = final_events[-1]
        assert last_event_type == "error"

        status_response = httpx.get(f"{base_url}/v2/_poc/agent/stream/{run_id}", timeout=5)
        assert status_response.status_code == 200
    finally:
        with contextlib.suppress(Exception):
            proc1.kill()
            proc1.wait(timeout=5)
        if proc2 is not None:
            with contextlib.suppress(Exception):
                proc2.kill()
                proc2.wait(timeout=5)
