"""Ejecuta una investigación T-303 real desde consola, sin endpoints T-304."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.durability import get_run
from app.agent.runner import create_run, execute_agent_run_async
from app.agent.worker_lease import mark_worker_shutdown, register_worker_instance
from app.config import get_settings
from app.db.engine import create_app_async_engine


async def _run(question: str) -> int:
    settings = get_settings()
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    worker_id: str | None = None
    try:
        worker_id = await register_worker_instance(engine, settings.worker_lease_ttl_s)
        run_id = await create_run(
            engine,
            worker_instance_id=worker_id,
            question=question,
            retention_user_days=settings.retention_user_days,
        )
    finally:
        await engine.dispose()

    await execute_agent_run_async(settings, run_id)

    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        run = await get_run(engine, run_id)
        if worker_id is not None:
            await mark_worker_shutdown(engine, worker_id)
        if run is None:
            print(json.dumps({"run_id": str(run_id), "status": "missing"}, ensure_ascii=False))
            return 1
        output = run.final_answer or {
            "run_id": str(run_id),
            "status": run.status,
            "terminal_error_code": run.terminal_error_code,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 0 if run.status in {"completed", "no_evidence"} else 1
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecutar el grafo real T-303")
    parser.add_argument("--question", required=True, help="Pregunta en lenguaje natural")
    args = parser.parse_args()
    if sys.platform == "win32":
        return asyncio.run(_run(args.question), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(_run(args.question))


if __name__ == "__main__":
    raise SystemExit(main())
