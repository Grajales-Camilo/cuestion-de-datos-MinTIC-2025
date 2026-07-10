"""Orquestacion de una corrida del grafo de juguete (T-300).

Cancelacion cooperativa para DELETE de corrida activa (contracts/api-rest.md
§7b): un `threading.Event` compartido, revisado entre cada paso del grafo y
durante la espera artificial entre pasos. Cancelar el `asyncio.Task` que
envuelve `asyncio.to_thread(...)` NO interrumpe el hilo subyacente (Python no
puede matar un hilo a la fuerza), por eso la senal de parada es este evento
explicito, no `Task.cancel()`.

Todo el ciclo de vida de una corrida (motor SQLAlchemy, checkpointer,
esperas artificiales entre pasos) ocurre dentro de UNA sola llamada
`asyncio.to_thread(..., loop_factory=SelectorEventLoop)` en Windows: un
unico loop para toda la corrida evita el problema de reabrir conexiones
psycopg-async en loops distintos entre pasos.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.durability import touch_run_heartbeat, write_terminal_event_once
from app.agent.toy_graph import NODES, build_toy_graph
from app.db.engine import create_app_async_engine
from app.db.models import AgentRun
from app.schemas import ErrorDetail, ErrorEnvelope

DEFAULT_STEP_DELAY_S = 1.0
CANCEL_POLL_INTERVAL_S = 0.2


@dataclass
class ActiveRun:
    task: asyncio.Task
    cancel_event: threading.Event = field(default_factory=threading.Event)


ACTIVE_RUNS: dict[uuid.UUID, ActiveRun] = {}


async def create_run(
    engine: AsyncEngine,
    *,
    worker_instance_id: str,
    question: str,
    retention_user_days: int,
) -> uuid.UUID:
    """Crea la fila `agent_runs` (status=running) para el PoC.

    Genera y descarta un `run_access_token` inmediatamente: las columnas
    `run_access_token_hash`/`run_access_token_expires_at` son NOT NULL en
    data-model.md, pero RF-801 (autorizacion Bearer) queda fuera de alcance
    de T-300 (pertenece a T-304) -- ver decision de alcance del plan.
    """

    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                question=question,
                status="running",
                worker_instance_id=worker_instance_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash=token_hash,
                run_access_token_expires_at=now + timedelta(days=retention_user_days),
                retention_class="user",
                created_at=now,
            )
        )
    return run_id


def start_run_task(
    sqlalchemy_database_url: str, psycopg_database_url: str, run_id: uuid.UUID, step_delay_s: float
) -> None:
    """Lanza la corrida como tarea cancelable y la registra para DELETE.

    Recibe las DOS formas de la URL (config.py): `sqlalchemy_database_url`
    (`postgresql+psycopg://...`) para el engine SQLAlchemy y
    `psycopg_database_url` (`postgresql://...` sin prefijo) para
    `AsyncPostgresSaver.from_conn_string`, igual que `db/checkpointer.py`.
    """

    cancel_event = threading.Event()
    task = asyncio.create_task(
        _execute_toy_run(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        )
    )
    ACTIVE_RUNS[run_id] = ActiveRun(task=task, cancel_event=cancel_event)
    task.add_done_callback(lambda _task: ACTIVE_RUNS.pop(run_id, None))


async def request_cancel_and_wait(run_id: uuid.UUID, grace_s: float) -> None:
    """DELETE de corrida activa (api-rest.md §7b): pide parada cooperativa y
    espera un plazo corto; si no coopera a tiempo, el llamador continua con
    el borrado de todos modos (la tarea puede seguir corriendo en segundo
    plano y sus escrituras posteriores fallaran silenciosamente porque la
    fila ya no existira)."""

    active = ACTIVE_RUNS.get(run_id)
    if active is None:
        return
    active.cancel_event.set()
    try:
        await asyncio.wait_for(asyncio.shield(active.task), timeout=grace_s)
    except TimeoutError:
        pass


async def _execute_toy_run(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(
            _run_with_selector,
            sqlalchemy_database_url,
            psycopg_database_url,
            run_id,
            step_delay_s,
            cancel_event,
        )
    else:
        await _execute_toy_run_async(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        )


def _run_with_selector(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    asyncio.run(
        _execute_toy_run_async(
            sqlalchemy_database_url, psycopg_database_url, run_id, step_delay_s, cancel_event
        ),
        loop_factory=asyncio.SelectorEventLoop,
    )


async def _execute_toy_run_async(
    sqlalchemy_database_url: str,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    step_delay_s: float,
    cancel_event: threading.Event,
) -> None:
    engine = create_app_async_engine(sqlalchemy_database_url, pool_pre_ping=True)
    try:
        config = {"configurable": {"thread_id": str(run_id)}}
        state = {"run_id": str(run_id), "steps_done": []}
        async with AsyncPostgresSaver.from_conn_string(psycopg_database_url) as saver:
            graph = build_toy_graph(engine, run_id, saver)
            for index in range(len(NODES)):
                if await _sleep_cancelable(step_delay_s, cancel_event):
                    return
                state = await graph.ainvoke(
                    state if index == 0 else None, config, durability="sync"
                )
                await touch_run_heartbeat(engine, run_id)
        await write_terminal_event_once(
            engine,
            run_id,
            status="completed",
            error_code=None,
            payload={
                "run_id": str(run_id),
                "status": "completed",
                "summary": (
                    "Demostracion T-300 completada: los "
                    f"{len(NODES)} pasos del grafo de juguete se ejecutaron."
                ),
                "usage": {"steps_used": len(NODES)},
            },
        )
    except Exception as exc:
        try:
            await write_terminal_event_once(
                engine,
                run_id,
                status="failed",
                error_code="INTERNAL",
                payload=ErrorEnvelope(
                    error=ErrorDetail(
                        code="INTERNAL",
                        status="failed",
                        message_user="Ocurrio un error inesperado en la demostracion.",
                        message_dev=str(exc),
                        retryable=False,
                    )
                ).model_dump(),
            )
        except Exception:
            pass
    finally:
        await engine.dispose()


async def _sleep_cancelable(total_s: float, cancel_event: threading.Event) -> bool:
    """Duerme en incrementos cortos para responder rapido a `cancel_event`.

    Devuelve True si debe abortarse (cancelado durante o antes de la espera).
    """

    remaining = total_s
    while remaining > 0:
        if cancel_event.is_set():
            return True
        step = min(CANCEL_POLL_INTERVAL_S, remaining)
        await asyncio.sleep(step)
        remaining -= step
    return cancel_event.is_set()
