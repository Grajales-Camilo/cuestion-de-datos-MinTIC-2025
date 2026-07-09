"""Auditoria de cobertura de publicadores oficiales (T-201A, research.md #7).

Mide, contra el catalogo ya ingerido por T-201, cuantos datasets tabulares
activos quedan `verified` contra el fixture de publicadores oficiales,
lista los aliases no unicos (`ambiguous=true`) ya registrados -- que nunca
asignan publicador automaticamente -- y prioriza por volumen de datasets
los textos de `publisher` que no resolvieron, para guiar la ampliacion
manual del fixture (`backend/data/official_publishers.json`) con
procedencia verificable. No decide ni asigna publicadores: solo mide y
prioriza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CatalogDataset, OfficialPublisherAlias

COVERAGE_TARGET = 0.90
DEFAULT_CANDIDATE_LIMIT = 100


@dataclass
class AmbiguousAliasGroup:
    alias_normalized: str
    publisher_ids: list[str]


@dataclass
class UnresolvedCandidate:
    publisher_text: str
    dataset_count: int
    sample_dataset_ids: list[str]


@dataclass
class CoverageReport:
    generated_at: datetime
    total_datasets: int
    total_active_datasets: int
    counts_by_status: dict[str, int]
    verified_ratio_active: float
    coverage_target: float
    coverage_gap: bool
    ambiguous_aliases: list[AmbiguousAliasGroup]
    unresolved_candidates: list[UnresolvedCandidate]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_datasets": self.total_datasets,
            "total_active_datasets": self.total_active_datasets,
            "counts_by_status": self.counts_by_status,
            "verified_ratio_active": round(self.verified_ratio_active, 4),
            "coverage_target": self.coverage_target,
            "coverage_gap": self.coverage_gap,
            "gap_explanation": _gap_explanation(self),
            "ambiguous_aliases": [
                {"alias_normalized": group.alias_normalized, "publisher_ids": group.publisher_ids}
                for group in self.ambiguous_aliases
            ],
            "unresolved_publisher_candidates": [
                {
                    "publisher_text": candidate.publisher_text,
                    "dataset_count": candidate.dataset_count,
                    "sample_dataset_ids": candidate.sample_dataset_ids,
                }
                for candidate in self.unresolved_candidates
            ],
        }


def _gap_explanation(report: CoverageReport) -> str | None:
    if not report.coverage_gap:
        return None
    return (
        f"Cobertura verified {report.verified_ratio_active:.2%} de datasets tabulares "
        f"activos, por debajo del objetivo {report.coverage_target:.0%} "
        "(research.md #7, tasks.md T-201A). Brecha documentada explicitamente, tal "
        "como permite el criterio de aceptacion; unresolved_publisher_candidates "
        "prioriza por volumen las siguientes ampliaciones del fixture."
    )


def build_coverage_report(
    *,
    counts_by_status: dict[str, int],
    total_datasets: int,
    total_active_datasets: int,
    ambiguous_aliases: list[AmbiguousAliasGroup],
    unresolved_candidates: list[UnresolvedCandidate],
    generated_at: datetime | None = None,
    coverage_target: float = COVERAGE_TARGET,
) -> CoverageReport:
    """Funcion pura (testeable sin DB): agrega conteos ya consultados en el
    reporte final y decide si hay brecha explicita frente al objetivo."""

    verified = counts_by_status.get("verified", 0)
    ratio = verified / total_active_datasets if total_active_datasets else 0.0
    return CoverageReport(
        generated_at=generated_at or datetime.now(UTC),
        total_datasets=total_datasets,
        total_active_datasets=total_active_datasets,
        counts_by_status=counts_by_status,
        verified_ratio_active=ratio,
        coverage_target=coverage_target,
        coverage_gap=ratio < coverage_target,
        ambiguous_aliases=ambiguous_aliases,
        unresolved_candidates=unresolved_candidates,
    )


async def fetch_counts_by_status(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(CatalogDataset.publisher_verification_status, func.count())
            .where(CatalogDataset.api_active.is_(True))
            .group_by(CatalogDataset.publisher_verification_status)
        )
    ).all()
    return dict(rows)


async def fetch_total_counts(session: AsyncSession) -> tuple[int, int]:
    total = (await session.execute(select(func.count()).select_from(CatalogDataset))).scalar_one()
    active = (
        await session.execute(select(func.count()).where(CatalogDataset.api_active.is_(True)))
    ).scalar_one()
    return total, active


async def fetch_ambiguous_aliases(session: AsyncSession) -> list[AmbiguousAliasGroup]:
    """Aliases ya marcados `ambiguous=true` en el registro (nunca asignan
    publicador automaticamente); se listan agrupados para revision manual,
    no para resolverlos aqui."""

    rows = (
        await session.execute(
            select(OfficialPublisherAlias.alias_normalized, OfficialPublisherAlias.publisher_id)
            .where(OfficialPublisherAlias.ambiguous.is_(True))
            .order_by(OfficialPublisherAlias.alias_normalized)
        )
    ).all()
    grouped: dict[str, list[str]] = {}
    for alias_normalized, publisher_id in rows:
        grouped.setdefault(alias_normalized, []).append(publisher_id)
    return [
        AmbiguousAliasGroup(alias_normalized=alias, publisher_ids=ids)
        for alias, ids in grouped.items()
    ]


async def fetch_unresolved_candidates(
    session: AsyncSession, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> list[UnresolvedCandidate]:
    """Textos crudos de `publisher` que quedaron `unknown`, priorizados por
    volumen de datasets tabulares activos: son los candidatos de mayor
    impacto para ampliar el fixture manualmente."""

    rows = (
        await session.execute(
            select(
                CatalogDataset.publisher,
                func.count(),
                func.array_agg(CatalogDataset.id),
            )
            .where(
                CatalogDataset.api_active.is_(True),
                CatalogDataset.publisher_verification_status == "unknown",
                CatalogDataset.publisher.is_not(None),
            )
            .group_by(CatalogDataset.publisher)
            .order_by(func.count().desc(), CatalogDataset.publisher)
            .limit(limit)
        )
    ).all()
    return [
        UnresolvedCandidate(
            publisher_text=publisher_text,
            dataset_count=count,
            sample_dataset_ids=sorted(dataset_ids)[:5],
        )
        for publisher_text, count, dataset_ids in rows
    ]


async def build_coverage_report_from_db(
    session: AsyncSession,
    coverage_target: float = COVERAGE_TARGET,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> CoverageReport:
    counts_by_status = await fetch_counts_by_status(session)
    total_datasets, total_active_datasets = await fetch_total_counts(session)
    ambiguous_aliases = await fetch_ambiguous_aliases(session)
    unresolved_candidates = await fetch_unresolved_candidates(session, limit=candidate_limit)
    return build_coverage_report(
        counts_by_status=counts_by_status,
        total_datasets=total_datasets,
        total_active_datasets=total_active_datasets,
        ambiguous_aliases=ambiguous_aliases,
        unresolved_candidates=unresolved_candidates,
        coverage_target=coverage_target,
    )
