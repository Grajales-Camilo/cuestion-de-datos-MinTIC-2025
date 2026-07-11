"""CLI para cargar las tipologias territoriales del DNP (T-207).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/load_tipologias_dnp.py --archivo RUTA --vigencia 2026

El DNP no publica una URL estable por vigencia (nombre de archivo distinto
cada ano -- ver research.md §18): el archivo "Base de Datos y Resultados"
se descarga a mano desde colaboracion.dnp.gov.co y se pasa como argumento
local. Requiere que `divipola_entries` (T-202) ya este cargada: un
`divipola_code` desconocido se reporta y se salta, no rompe la carga.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.db.tipologias import read_workbook_entries, upsert_territorio_tipologia


async def _run(archivo: str, vigencia: int) -> None:
    entries = read_workbook_entries(archivo, vigencia)

    settings = get_settings()
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        summary = await upsert_territorio_tipologia(engine, entries)
    finally:
        await engine.dispose()

    municipios = sum(1 for entry in entries if entry.level == "municipality")
    departamentos = sum(1 for entry in entries if entry.level == "department")
    print(
        f"Filas leidas: {len(entries)} | municipios: {municipios} | "
        f"departamentos: {departamentos} | creados: {summary.entries_created} | "
        f"actualizados: {summary.entries_updated} | "
        f"saltados (divipola_code desconocido): {len(summary.skipped_missing_divipola)}"
    )
    if summary.skipped_missing_divipola:
        print("Codigos saltados:", ", ".join(summary.skipped_missing_divipola))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Carga las tipologias territoriales del DNP (T-207)."
    )
    parser.add_argument(
        "--archivo",
        required=True,
        help="Ruta local al archivo 'Base de Datos y Resultados' descargado del DNP.",
    )
    parser.add_argument(
        "--vigencia",
        type=int,
        required=True,
        help="Ano de vigencia de la tipologia (p. ej. 2026).",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(_run(args.archivo, args.vigencia), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_run(args.archivo, args.vigencia))


if __name__ == "__main__":
    main()
