"""CLI para cargar el maestro DIVIPOLA (T-202).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/load_divipola.py [--dataset-id ID] [--page-size N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.divipola_client import DivipolaClient
from app.config import get_settings
from app.db.divipola import rows_to_entries, upsert_divipola_entries

_SODA_BASE_URL = "https://www.datos.gov.co"
_DEFAULT_DATASET_ID = "gdxc-w37w"


async def _run(dataset_id: str, page_size: int) -> None:
    settings = get_settings()
    app_token = (
        settings.socrata_app_token.get_secret_value() if settings.socrata_app_token else None
    )

    rows: list[dict] = []
    async with httpx.AsyncClient(base_url=_SODA_BASE_URL) as http_client:
        client = DivipolaClient(http_client, dataset_id=dataset_id, app_token=app_token)
        async for page in client.iter_rows(page_size=page_size):
            rows.extend(page)

    entries = rows_to_entries(rows)

    engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await upsert_divipola_entries(engine, entries)
    finally:
        await engine.dispose()

    municipalities = sum(1 for entry in entries if entry.level == "municipality")
    departments = sum(1 for entry in entries if entry.level == "department")
    print(
        f"Filas fuente: {len(rows)} | departamentos: {departments} | "
        f"municipios: {municipalities} | "
        f"creados: {summary.entries_created} | actualizados: {summary.entries_updated}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga el maestro DIVIPOLA (T-202).")
    parser.add_argument(
        "--dataset-id",
        default=_DEFAULT_DATASET_ID,
        help=f"Id del dataset SODA en datos.gov.co (default: {_DEFAULT_DATASET_ID}).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Filas por pagina SODA (default: 1000).",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            _run(args.dataset_id, args.page_size), loop_factory=asyncio.SelectorEventLoop
        )
    else:
        asyncio.run(_run(args.dataset_id, args.page_size))


if __name__ == "__main__":
    main()
