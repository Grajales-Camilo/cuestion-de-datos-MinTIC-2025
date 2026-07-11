"""Ejecuta una vez el barrido externo de retención (T-306, RF-804)."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.retention_sweep import run_retention_sweep
from app.config import get_settings
from app.db.engine import create_app_async_engine


async def _run() -> int:
    settings = get_settings()
    salt = settings.retention_hash_salt.get_secret_value() if settings.retention_hash_salt else None
    if not salt:
        raise RuntimeError(
            "RETENTION_HASH_SALT es obligatorio para ejecutar el barrido de retención."
        )

    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await run_retention_sweep(
            engine,
            settings.psycopg_database_url,
            now=datetime.now(UTC),
            retention_user_days=settings.retention_user_days,
            retention_eval_months=settings.retention_eval_months,
            retention_tech_months=settings.retention_tech_months,
            retention_hash_salt=salt,
        )
    finally:
        await engine.dispose()
    print(json.dumps(summary.as_api_response(), ensure_ascii=False))
    return 0


def main() -> int:
    if sys.platform == "win32":
        return asyncio.run(_run(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
