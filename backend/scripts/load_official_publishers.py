"""CLI para cargar el fixture de publicadores oficiales (T-106).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/load_official_publishers.py [--fixture RUTA]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.db.publishers import DEFAULT_FIXTURE_PATH, load_fixture, reload_official_publishers


async def _run(fixture_path: Path) -> None:
    settings = get_settings()
    fixture = load_fixture(fixture_path)
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await reload_official_publishers(engine, fixture)
    finally:
        await engine.dispose()

    print(
        f"Publicadores creados: {summary.publishers_created} | "
        f"actualizados: {summary.publishers_updated} | "
        f"alias cargados: {summary.aliases_created} | "
        f"alias ambiguos: {summary.ambiguous_aliases}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Carga el registro canonico de publicadores oficiales."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Ruta al fixture JSON versionado (default: backend/data/official_publishers.json).",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(_run(args.fixture), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_run(args.fixture))


if __name__ == "__main__":
    main()
