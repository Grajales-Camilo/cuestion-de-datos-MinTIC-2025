"""CLI para congelar la muestra fija del benchmark de embeddings (T-205).

research.md §1, procedimiento de benchmark, literal (b): "muestra fija de
metadatos ya ingeridos (T-201) y maestro DIVIPOLA cargado (T-202),
congelados como fixture". Este script NO es el benchmark: solo exporta un
snapshot reproducible de Postgres a JSON versionado en
`notebooks/fixtures/`, para que el notebook nunca dependa de una base viva
(evita que el catálogo cambie entre corridas del benchmark y rompa la
comparabilidad de resultados).

Uso (desde backend/, con la base local de T-105 arriba):
    python scripts/export_benchmark_fixture.py [--catalog-limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "notebooks" / "fixtures"

_CATALOG_QUERY = text(
    """
    SELECT id, name, description, publisher, category, embedding_text,
           data_updated_at, eligibility_status
    FROM catalog_datasets
    WHERE api_active = true AND embedding_text IS NOT NULL
    ORDER BY id
    LIMIT :limit
    """
)

_DIVIPOLA_QUERY = text(
    """
    SELECT code, name, department_code, department_name, level,
           name_normalized, alt_names
    FROM divipola_entries
    ORDER BY level, code
    """
)


def _row_to_dict(row) -> dict:
    data = dict(row._mapping)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


async def _export(catalog_limit: int, output_dir: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            catalog_rows = [
                _row_to_dict(row)
                for row in (
                    await connection.execute(_CATALOG_QUERY, {"limit": catalog_limit})
                ).all()
            ]
            divipola_rows = [
                _row_to_dict(row) for row in (await connection.execute(_DIVIPOLA_QUERY)).all()
            ]
    finally:
        await engine.dispose()

    if not catalog_rows:
        raise SystemExit(
            "catalog_datasets no devolvio filas elegibles (api_active=true, "
            "embedding_text no nulo). Corre scripts/ingest_catalog.py antes de exportar."
        )
    if not divipola_rows:
        raise SystemExit(
            "divipola_entries esta vacio. Corre scripts/load_divipola.py antes de exportar."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    exported_at = datetime.now(UTC).isoformat()

    catalog_path = output_dir / "catalog_sample.json"
    catalog_path.write_text(
        json.dumps(
            {
                "exported_at": exported_at,
                "source_query": str(_CATALOG_QUERY),
                "count": len(catalog_rows),
                "datasets": catalog_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    divipola_path = output_dir / "divipola_master.json"
    divipola_path.write_text(
        json.dumps(
            {
                "exported_at": exported_at,
                "count": len(divipola_rows),
                "entries": divipola_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    top_categories = Counter(row["category"] or "(sin categoria)" for row in catalog_rows)
    print(f"catalog_sample.json: {len(catalog_rows)} datasets -> {catalog_path}")
    print("Top 10 categorias en la muestra:")
    for category, count in top_categories.most_common(10):
        print(f"  {count:4d}  {category}")
    print(f"divipola_master.json: {len(divipola_rows)} entradas -> {divipola_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Congela la muestra fija del benchmark de embeddings (T-205)."
    )
    parser.add_argument(
        "--catalog-limit",
        type=int,
        default=500,
        help="Numero maximo de datasets a incluir en la muestra (default: 500).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_OUTPUT_DIR,
        help=f"Directorio de salida (default: {_OUTPUT_DIR}).",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            _export(args.catalog_limit, args.output_dir), loop_factory=asyncio.SelectorEventLoop
        )
    else:
        asyncio.run(_export(args.catalog_limit, args.output_dir))


if __name__ == "__main__":
    main()
