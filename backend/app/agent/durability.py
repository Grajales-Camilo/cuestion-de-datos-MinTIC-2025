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

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import AgentRun, AgentRunEvent, TechnicalMetric

EventType = Literal["step", "evidence", "answer", "error"]
TerminalStatus = Literal["completed", "no_evidence", "interrupted", "failed"]
DeletionReason = Literal["user_requested", "retention_expired"]


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
    async with session_factory() as session, session.begin():
        seq = await reserve_and_add_event(session, run_id, event_type, payload)
    return EmittedEvent(run_id=run_id, seq=seq, event_type=event_type, payload=payload)


async def reserve_and_add_event(
    session: AsyncSession,
    run_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
) -> int:
    """Reserva e inserta un evento usando la transacción activa del llamador."""

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
            created_at=datetime.now(UTC),
        )
    )
    return int(seq)


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


async def delete_run_with_metrics(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    *,
    deletion_reason: DeletionReason,
    retention_hash_salt: str,
) -> bool:
    """Copia métricas no identificables a `technical_metrics` y borra la
    corrida, en la misma transacción (RF-803/RF-804, data-model.md §7,
    research.md §4: "Al vencer la retención (o ante borrado por solicitud,
    que tiene prioridad): borrado completo... tras copiar métricas
    agregadas no identificables a `technical_metrics`").

    `source_run_hash = sha256(run_id + RETENTION_HASH_SALT)` es UNIQUE:
    `ON CONFLICT DO NOTHING` hace la copia idempotente ante un reintento
    (p. ej. si un fallo posterior obliga a repetir el borrado) sin duplicar
    la métrica ni fallar por violar la restricción.
    """

    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        run = await session.get(AgentRun, run_id)
        if run is None:
            return False
        source_run_hash = hashlib.sha256(f"{run_id}{retention_hash_salt}".encode()).hexdigest()
        await session.execute(
            pg_insert(TechnicalMetric)
            .values(
                id=uuid.uuid4(),
                run_month=run.created_at.strftime("%Y-%m"),
                source_run_hash=source_run_hash,
                retention_class_origin=run.retention_class,
                status_final=run.status,
                llm_provider=run.llm_provider,
                llm_model=run.llm_model,
                steps_used=run.steps_used,
                latency_ms=run.latency_ms,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                estimated_cost_usd=run.estimated_cost_usd,
                deleted_at=now,
                deletion_reason=deletion_reason,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["source_run_hash"])
        )
        await session.execute(delete(AgentRun).where(AgentRun.id == run_id))
    return True


async def delete_run_with_checkpoints(
    engine: AsyncEngine,
    psycopg_database_url: str,
    run_id: uuid.UUID,
    *,
    deletion_reason: DeletionReason,
    retention_hash_salt: str,
) -> bool:
    """Borra checkpoints y después la corrida con sus métricas agregadas.

    Es la única operación compartida por RF-803 y RF-804. Si `adelete_thread`
    falla, la corrida permanece intacta; si falla la transacción posterior, el
    checkpoint ya no existe pero el siguiente intento repite el procedimiento
    sin duplicar métricas gracias a `source_run_hash` único.
    """

    async with AsyncPostgresSaver.from_conn_string(psycopg_database_url) as saver:
        await saver.adelete_thread(str(run_id))
    return await delete_run_with_metrics(
        engine,
        run_id,
        deletion_reason=deletion_reason,
        retention_hash_salt=retention_hash_salt,
    )
