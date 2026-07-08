"""CLI de ingesta del catalogo de datos.gov.co (T-201).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/ingest_catalog.py [--limit N] [--page-size N]
        [--trigger manual|cron] [--domain DOMINIO]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.ingest import run_ingest
from app.config import get_settings


async def _run(limit: int | None, page_size: int, trigger: str, domain: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await run_ingest(
            engine,
            settings,
            trigger=trigger,  # type: ignore[arg-type]
            limit=limit,
            page_size=page_size,
            domain=domain,
        )
    finally:
        await engine.dispose()

    print(
        f"Ingest run: {summary.ingest_run_id} | "
        f"nuevos: {summary.datasets_new} | actualizados: {summary.datasets_updated} | "
        f"fallidos: {summary.datasets_failed}"
    )
    if summary.error_summary:
        print(f"Primeros errores ({len(summary.error_summary)}):")
        for entry in summary.error_summary[:10]:
            print(f"  - {entry['dataset_id']}: {entry['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta el catalogo de datos.gov.co via la Discovery API de Socrata."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita el total de datasets procesados (muestra de desarrollo; "
        "sin este flag NO se reconcilia api_active de datasets no vistos).",
    )
    parser.add_argument(
        "--page-size", type=int, default=1000, help="Tamano de pagina de Discovery API."
    )
    parser.add_argument("--trigger", choices=["manual", "cron"], default="manual")
    parser.add_argument("--domain", default="www.datos.gov.co")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            _run(args.limit, args.page_size, args.trigger, args.domain),
            loop_factory=asyncio.SelectorEventLoop,
        )
    else:
        asyncio.run(_run(args.limit, args.page_size, args.trigger, args.domain))


if __name__ == "__main__":
    main()
