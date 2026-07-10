"""Primitivas de durabilidad de corridas (T-300, plan.md §11).

`reserve_and_emit_event` implementa la reserva atomica de `seq` (data-model.md
agent_runs): `UPDATE agent_runs SET last_event_seq = last_event_seq + 1
WHERE id = :run_id RETURNING last_event_seq` seguido de la insercion en
`agent_run_events`, ambos en la MISMA transaccion. `write_terminal_event_once`
combina esa misma reserva con un UPDATE condicional sobre
`terminal_event_written_at` para garantizar como maximo un evento terminal
(`answer`/`error`) aunque compitan timeout, worker perdido, reinicio o un
reintento.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import AgentRun, AgentRunEvent

EventType = Literal["step", "evidence", "answer", "error"]
TerminalStatus = Literal["completed", "no_evidence", "interrupted", "failed"]


@dataclass
class EmittedEvent:
    run_id: uuid.UUID
    seq: int
    event_type: str
    payload: dict[str, Any]


async def reserve_and_emit_event(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
) -> EmittedEvent:
    """Reserva `seq` atomicamente e inserta el evento en la MISMA transaccion.

    Dos emisores concurrentes sobre la misma corrida serializan por el
    bloqueo de fila que impone el UPDATE de `agent_runs`; nunca se calcula
    `MAX(seq)+1` fuera de una transaccion (data-model.md §3).
    """

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        seq = (
            await session.execute(
                text(
                    "UPDATE agent_runs SET last_event_seq = last_event_seq + 1 "
                    "WHERE id = :run_id RETURNING last_event_seq"
                ),
                {"run_id": run_id},
            )
        ).scalar_one()
        session.add(
            AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                payload=payload,
                created_at=now,
            )
        )
    return EmittedEvent(run_id=run_id, seq=seq, event_type=event_type, payload=payload)


async def write_terminal_event_once(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    *,
    status: TerminalStatus,
    error_code: str | None,
    payload: dict[str, Any],
) -> EmittedEvent | None:
    """Escribe el evento terminal (`answer`/`error`) como maximo una vez.

    El UPDATE condicional `WHERE terminal_event_written_at IS NULL` reserva
    `seq` y marca el estado terminal en una sola sentencia atomica: solo una
    transaccion concurrente puede ganarla (bloqueo de fila + condicion). Las
    demas (timeout compitiendo con un evento normal, detector de worker
    perdido, reintento tras un fallo transitorio) ven `rowcount == 0` y no
    escriben nada. Devuelve `None` cuando la corrida ya tenia un evento
    terminal (idempotencia observable para llamadas repetidas).
    """

    event_type: EventType = "answer" if status in ("completed", "no_evidence") else "error"
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        result = await session.execute(
            text(
                "UPDATE agent_runs SET status = :status, terminal_error_code = :error_code, "
                "terminal_event_written_at = :now, last_event_seq = last_event_seq + 1 "
                "WHERE id = :run_id AND terminal_event_written_at IS NULL "
                "RETURNING last_event_seq"
            ),
            {"status": status, "error_code": error_code, "now": now, "run_id": run_id},
        )
        row = result.first()
        if row is None:
            return None
        seq = row[0]
        session.add(
            AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                payload=payload,
                created_at=now,
            )
        )
    return EmittedEvent(run_id=run_id, seq=seq, event_type=event_type, payload=payload)


async def touch_run_heartbeat(engine: AsyncEngine, run_id: uuid.UUID) -> None:
    """Actualiza `heartbeat_at`; base de la deteccion de huerfanas (plan.md §11)."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(AgentRun).where(AgentRun.id == run_id).values(heartbeat_at=datetime.now(UTC))
        )


async def list_events_since(
    engine: AsyncEngine, run_id: uuid.UUID, since_seq: int
) -> list[AgentRunEvent]:
    """Eventos persistidos con `seq > since_seq`, para reconexion `Last-Event-ID`."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id, AgentRunEvent.seq > since_seq)
                .order_by(AgentRunEvent.seq)
            )
        ).scalars().all()
    return list(rows)


async def get_run(engine: AsyncEngine, run_id: uuid.UUID) -> AgentRun | None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        return await session.get(AgentRun, run_id)
