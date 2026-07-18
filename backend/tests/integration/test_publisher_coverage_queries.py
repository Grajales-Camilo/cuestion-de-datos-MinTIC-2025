"""Integracion T-201A: consultas reales de auditoria de cobertura de publicadores."""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.catalog.coverage import build_coverage_report_from_db
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import CatalogDataset, OfficialPublisher, OfficialPublisherAlias

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine(isolated_database_url):
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


def _dataset(id_: str, publisher: str, status: str, api_active: bool = True) -> CatalogDataset:
    now = datetime.now(UTC)
    return CatalogDataset(
        id=id_,
        name=f"Dataset {id_}",
        publisher=publisher,
        publisher_verification_status=status,
        metadata_synced_at=now,
        api_active=api_active,
        embedding_text="texto",
    )


@pytest.fixture
async def seeded_catalog(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            OfficialPublisher(
                id="dane",
                canonical_name="Departamento Administrativo Nacional de Estadística",
                normalized_name="DEPARTAMENTO ADMINISTRATIVO NACIONAL DE ESTADISTICA",
                entity_type="departamento_administrativo",
                active=True,
                verification_source="prueba de integración T-201A",
                updated_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add_all(
            [
                _dataset("aaaa-0001", "DANE", "verified"),
                _dataset("aaaa-0002", "DANE", "verified"),
                _dataset("aaaa-0003", "Entidad Desconocida", "unknown"),
                _dataset("aaaa-0004", "Entidad Desconocida", "unknown"),
                _dataset("aaaa-0005", "Entidad Desconocida", "unknown"),
                _dataset("aaaa-0006", "Universidad Privada X", "private_or_non_official"),
                _dataset("aaaa-0007", "DANE", "verified", api_active=False),
            ]
        )
        session.add(
            OfficialPublisherAlias(
                publisher_id="dane",
                alias_normalized="ALIAS AMBIGUO DE PRUEBA",
                alias_raw="Alias Ambiguo de Prueba",
                ambiguous=True,
                verification_source="prueba de integracion T-201A",
                created_at=datetime.now(UTC),
            )
        )

    yield


async def test_report_counts_only_active_datasets(engine, seeded_catalog) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        report = await build_coverage_report_from_db(session)

    assert report.total_datasets == 7
    assert report.total_active_datasets == 6
    assert report.counts_by_status == {
        "verified": 2,
        "unknown": 3,
        "private_or_non_official": 1,
    }
    assert report.verified_ratio_active == pytest.approx(2 / 6)
    assert report.coverage_gap is True


async def test_report_prioritizes_unresolved_candidates_by_volume(engine, seeded_catalog) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        report = await build_coverage_report_from_db(session)

    assert report.unresolved_candidates[0].publisher_text == "Entidad Desconocida"
    assert report.unresolved_candidates[0].dataset_count == 3
    assert report.unresolved_candidates[0].sample_dataset_ids == [
        "aaaa-0003",
        "aaaa-0004",
        "aaaa-0005",
    ]


async def test_report_lists_ambiguous_aliases(engine, seeded_catalog) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        report = await build_coverage_report_from_db(session)

    assert len(report.ambiguous_aliases) == 1
    assert report.ambiguous_aliases[0].alias_normalized == "ALIAS AMBIGUO DE PRUEBA"
    assert report.ambiguous_aliases[0].publisher_ids == ["dane"]
