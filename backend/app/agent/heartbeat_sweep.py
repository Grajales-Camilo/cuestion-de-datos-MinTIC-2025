"""Barrido periodico de corridas huerfanas (T-300, plan.md §11).

Tres chequeos independientes sobre corridas `running`, en este orden de
prioridad: (1) duracion maxima excedida -> `failed/RUN_TIMEOUT` (nunca
`interrupted`: research.md §2 distingue un limite operacional de una
interrupcion externa); (2) heartbeat propio de la corrida vencido ->
`interrupted/HEARTBEAT_EXPIRED`; (3) lease de la instancia duena vencida,
detectado DURANTE la operacion (no al arrancar) -> `interrupted/WORKER_LOST`.

Convencion adoptada para des-ambiguar `plan.md` §11 (que permite
`RUN_INTERRUPTED` *o* `WORKER_LOST` sin regla explicita): `RUN_INTERRUPTED`
lo escribe el arranque idempotente (`worker_lease.close_stale_running_runs`);
`WORKER_LOST` lo escribe este barrido periodico cuando la lease del worker
dueno vence mientras el proceso que hace el barrido sigue vivo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.durability import write_terminal_event_once
from app.db.models import AgentRun, WorkerInstance
from app.schemas import ErrorDetail, ErrorEnvelope


@dataclass
class SweepSummary:
    timed_out: list[uuid.UUID] = field(default_factory=list)
    heartbeat_expired: list[uuid.UUID] = field(default_factory=list)
    worker_lost: list[uuid.UUID] = field(default_factory=list)


def _error_payload(code: str, status: str, message_user: str, message_dev: str) -> dict:
    return ErrorEnvelope(
        error=ErrorDetail(
            code=code, status=status, message_user=message_user, message_dev=message_dev,
            retryable=True,
        )
    ).model_dump()


async def sweep_orphaned_runs(
    engine: AsyncEngine,
    *,
    own_worker_instance_id: str,
    heartbeat_timeout_s: int,
    max_duration_s: int,
) -> SweepSummary:
    now = datetime.now(UTC)
    summary = SweepSummary()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        running = (
            await session.execute(
                select(AgentRun, WorkerInstance)
                .join(WorkerInstance, WorkerInstance.id == AgentRun.worker_instance_id)
                .where(AgentRun.status == "running")
            )
        ).all()

    for run, worker in running:
        age_s = (now - run.created_at).total_seconds()
        if age_s > max_duration_s:
            result = await write_terminal_event_once(
                engine,
                run.id,
                status="failed",
                error_code="RUN_TIMEOUT",
                payload=_error_payload(
                    "RUN_TIMEOUT",
                    "failed",
                    "La investigacion supero el tiempo maximo permitido.",
                    f"age_s={age_s:.1f} > RUN_MAX_DURATION_S={max_duration_s}",
                ),
            )
            if result is not None:
                summary.timed_out.append(run.id)
            continue

        heartbeat_reference = run.heartbeat_at or run.created_at
        heartbeat_age_s = (now - heartbeat_reference).total_seconds()
        if heartbeat_age_s > heartbeat_timeout_s:
            result = await write_terminal_event_once(
                engine,
                run.id,
                status="interrupted",
                error_code="HEARTBEAT_EXPIRED",
                payload=_error_payload(
                    "HEARTBEAT_EXPIRED",
                    "interrupted",
                    "La investigacion dejo de reportar actividad. Puedes volver a ejecutarla.",
                    f"heartbeat_age_s={heartbeat_age_s:.1f} > "
                    f"RUN_HEARTBEAT_TIMEOUT_S={heartbeat_timeout_s}",
                ),
            )
            if result is not None:
                summary.heartbeat_expired.append(run.id)
            continue

        if worker.id != own_worker_instance_id and worker.lease_expires_at < now:
            result = await write_terminal_event_once(
                engine,
                run.id,
                status="interrupted",
                error_code="WORKER_LOST",
                payload=_error_payload(
                    "WORKER_LOST",
                    "interrupted",
                    "El proceso que ejecutaba esta investigacion desaparecio. "
                    "Puedes volver a ejecutarla.",
                    f"worker_instance_id={worker.id} "
                    f"lease_expires_at={worker.lease_expires_at.isoformat()}",
                ),
            )
            if result is not None:
                summary.worker_lost.append(run.id)

    return summary
