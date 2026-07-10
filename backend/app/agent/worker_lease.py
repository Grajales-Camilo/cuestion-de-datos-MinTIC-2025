"""Lease de `worker_instances` y arranque idempotente (T-300, plan.md §11).

Cada proceso genera un `worker_instance_id` propio y mantiene una lease con
TTL renovado periodicamente. Al arrancar, una instancia nueva marca como
`interrupted` SOLO las corridas `running` cuya instancia duena tenga la
lease vencida: un despliegue con dos procesos solapados no debe interrumpir
corridas sanas de una instancia con lease vigente (research.md §2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.durability import write_terminal_event_once
from app.db.models import AgentRun, WorkerInstance
from app.schemas import ErrorDetail, ErrorEnvelope


async def register_worker_instance(engine: AsyncEngine, ttl_s: int) -> str:
    """Crea una instancia nueva con lease activa. Devuelve su `worker_instance_id`."""

    worker_instance_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            WorkerInstance(
                id=worker_instance_id,
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=ttl_s),
                status="active",
            )
        )
    return worker_instance_id


async def renew_lease(engine: AsyncEngine, worker_instance_id: str, ttl_s: int) -> None:
    """Renueva heartbeat y lease. Politica normativa: cada `ttl_s / 3` (plan.md §11)."""

    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(WorkerInstance)
            .where(WorkerInstance.id == worker_instance_id)
            .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=ttl_s))
        )


async def mark_worker_shutdown(engine: AsyncEngine, worker_instance_id: str) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(WorkerInstance)
            .where(WorkerInstance.id == worker_instance_id)
            .values(status="shutdown")
        )


async def find_stale_running_run_ids(
    engine: AsyncEngine, own_worker_instance_id: str
) -> list[uuid.UUID]:
    """Corridas `running` cuya instancia duena tiene lease vencida.

    Excluye corridas sin `worker_instance_id` (no hay lease que evaluar) y
    corridas cuya instancia duena todavia tiene lease vigente.
    """

    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AgentRun.id)
                .join(WorkerInstance, WorkerInstance.id == AgentRun.worker_instance_id)
                .where(
                    AgentRun.status == "running",
                    WorkerInstance.id != own_worker_instance_id,
                    WorkerInstance.lease_expires_at < now,
                )
            )
        ).scalars().all()
    return list(rows)


async def close_stale_running_runs(engine: AsyncEngine, own_worker_instance_id: str) -> int:
    """Arranque idempotente: cierra huerfanas de instancias con lease vencida.

    Repetir el arranque no duplica el evento terminal: `write_terminal_event_once`
    es idempotente por `terminal_event_written_at`, y una corrida ya cerrada
    deja de ser `running` por lo que la siguiente pasada ni la selecciona.
    """

    stale_run_ids = await find_stale_running_run_ids(engine, own_worker_instance_id)
    closed = 0
    for run_id in stale_run_ids:
        result = await write_terminal_event_once(
            engine,
            run_id,
            status="interrupted",
            error_code="RUN_INTERRUPTED",
            payload=ErrorEnvelope(
                error=ErrorDetail(
                    code="RUN_INTERRUPTED",
                    status="interrupted",
                    message_user=(
                        "El servicio se reinicio mientras esta investigacion estaba en curso. "
                        "Puedes volver a ejecutarla."
                    ),
                    message_dev="Arranque idempotente: lease de la instancia duena vencida.",
                    retryable=True,
                )
            ).model_dump(),
        )
        if result is not None:
            closed += 1
    return closed
