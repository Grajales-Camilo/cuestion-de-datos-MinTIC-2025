"""CLI de auditoria de cobertura de publicadores oficiales (T-201A).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/audit_publisher_coverage.py [--output PATH] [--candidate-limit N]

No ingesta ni modifica `catalog_datasets`; solo lee el catalogo ya
ingerido por T-201 y escribe `backend/data/official_publishers_coverage.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.catalog.coverage import build_coverage_report_from_db
from app.config import get_settings

_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "data" / "official_publishers_coverage.json"
)


async def _run(output_path: Path, candidate_limit: int) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            report = await build_coverage_report_from_db(session, candidate_limit=candidate_limit)
    finally:
        await engine.dispose()

    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    verified = report.counts_by_status.get("verified", 0)
    print(
        f"Cobertura verified: {report.verified_ratio_active:.2%} "
        f"({verified}/{report.total_active_datasets}) | "
        f"objetivo: {report.coverage_target:.0%} | brecha: {report.coverage_gap}"
    )
    print(f"Aliases ambiguos: {len(report.ambiguous_aliases)}")
    print(f"Candidatos sin resolver: {len(report.unresolved_candidates)}")
    print(f"Reporte escrito en {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audita la cobertura de publicadores oficiales contra el catalogo "
            "ya ingerido (T-201A)."
        )
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--candidate-limit", type=int, default=100)
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            _run(args.output, args.candidate_limit), loop_factory=asyncio.SelectorEventLoop
        )
    else:
        asyncio.run(_run(args.output, args.candidate_limit))


if __name__ == "__main__":
    main()
