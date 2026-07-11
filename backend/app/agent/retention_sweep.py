"""Barrido idempotente de retención (T-306, RF-804)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.durability import delete_run_with_checkpoints

_LOCK_NAMESPACE = 20260707
_LOCK_KEY = 804


@dataclass(frozen=True)
class RetentionCounts:
    user_runs: int = 0
    eval_runs: int = 0
    technical_metrics: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "user_runs": self.user_runs,
            "eval_runs": self.eval_runs,
            "technical_metrics": self.technical_metrics,
        }


@dataclass(frozen=True)
class RetentionSweepSummary:
    already_running: bool
    planned: RetentionCounts
    executed: RetentionCounts

    def as_api_response(self) -> dict[str, object]:
        return {
            "status": "skipped" if self.already_running else "accepted",
            "reason": "already_running" if self.already_running else None,
            "planned": self.planned.as_dict(),
            "executed": self.executed.as_dict(),
        }


async def run_retention_sweep(
    engine: AsyncEngine,
    psycopg_database_url: str,
    *,
    now: datetime,
    retention_user_days: int,
    retention_eval_months: int,
    retention_tech_months: int,
    retention_hash_salt: str,
) -> RetentionSweepSummary:
    """Aplica RF-804 bajo un advisory lock transaccional de PostgreSQL.

    `now` es inyectable para pruebas de frontera. El lock se mantiene mientras
    se planifican y ejecutan los borrados; un segundo barrido sale sin efectos.
    Cada corrida se borra con la operación compartida de T-304, cuya copia con
    `ON CONFLICT DO NOTHING` permite reintentar después de un fallo sin crear
    una segunda métrica técnica.
    """

    if now.tzinfo is None:
        raise ValueError("now debe incluir zona horaria UTC")
    now = now.astimezone(UTC)

    async with engine.connect() as lock_connection, lock_connection.begin():
        acquired = (
            await lock_connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
                {"namespace": _LOCK_NAMESPACE, "key": _LOCK_KEY},
            )
        ).scalar_one()
        if not acquired:
            empty = RetentionCounts()
            return RetentionSweepSummary(already_running=True, planned=empty, executed=empty)

        expired_runs = (
            await lock_connection.execute(
                text(
                    "SELECT id, retention_class FROM agent_runs "
                    "WHERE (retention_class = 'user' "
                    "AND created_at + make_interval(days => CAST(:user_days AS integer)) < :now) "
                    "OR (retention_class = 'eval' AND created_at + "
                    "make_interval(months => CAST(:eval_months AS integer)) < :now)"
                ),
                {
                    "user_days": retention_user_days,
                    "eval_months": retention_eval_months,
                    "now": now,
                },
            )
        ).all()
        planned_metrics = int(
            (
                await lock_connection.execute(
                    text(
                        "SELECT count(*) FROM technical_metrics "
                        "WHERE created_at + make_interval(months => "
                        "CAST(:tech_months AS integer)) < :now"
                    ),
                    {"tech_months": retention_tech_months, "now": now},
                )
            ).scalar_one()
        )
        planned = RetentionCounts(
            user_runs=sum(retention_class == "user" for _, retention_class in expired_runs),
            eval_runs=sum(retention_class == "eval" for _, retention_class in expired_runs),
            technical_metrics=planned_metrics,
        )

        executed_user = 0
        executed_eval = 0
        for raw_run_id, retention_class in expired_runs:
            deleted = await delete_run_with_checkpoints(
                engine,
                psycopg_database_url,
                uuid.UUID(str(raw_run_id)),
                deletion_reason="retention_expired",
                retention_hash_salt=retention_hash_salt,
            )
            if deleted and retention_class == "user":
                executed_user += 1
            elif deleted and retention_class == "eval":
                executed_eval += 1

        purge_result = await lock_connection.execute(
            text(
                "DELETE FROM technical_metrics WHERE created_at + make_interval(months => "
                "CAST(:tech_months AS integer)) < :now"
            ),
            {"tech_months": retention_tech_months, "now": now},
        )
        return RetentionSweepSummary(
            already_running=False,
            planned=planned,
            executed=RetentionCounts(
                user_runs=executed_user,
                eval_runs=executed_eval,
                technical_metrics=purge_result.rowcount,
            ),
        )
