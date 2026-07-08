"""Integracion T-106/RF-401: carga y resolucion de publicadores oficiales contra Postgres real."""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import OfficialPublisherAlias
from app.db.publishers import load_fixture, reload_official_publishers, resolve_publisher

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def loaded_fixture(engine):
    fixture = load_fixture()
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM official_publisher_aliases"))
        await connection.execute(text("DELETE FROM official_publishers"))
    summary = await reload_official_publishers(engine, fixture)
    return fixture, summary


async def test_reload_creates_all_publishers_and_aliases(loaded_fixture) -> None:
    fixture, summary = loaded_fixture

    assert summary.publishers_created == len(fixture.publishers)
    assert summary.publishers_updated == 0
    total_aliases = sum(len(publisher.aliases) for publisher in fixture.publishers)
    assert summary.aliases_created == total_aliases
    assert summary.ambiguous_aliases == 2


async def test_reload_is_idempotent(engine, loaded_fixture) -> None:
    fixture, _ = loaded_fixture

    summary_again = await reload_official_publishers(engine, fixture)

    assert summary_again.publishers_created == 0
    assert summary_again.publishers_updated == len(fixture.publishers)
    total_aliases = sum(len(publisher.aliases) for publisher in fixture.publishers)
    assert summary_again.aliases_created == total_aliases


async def test_resolve_canonical_name(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(
            session, "Departamento Administrativo Nacional de Estadística"
        )

    assert resolution.status == "verified"
    assert resolution.official_publisher_id == "dane"


async def test_resolve_ignores_case_and_accents(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(session, "ministerio de educacion nacional")

    assert resolution.status == "verified"
    assert resolution.official_publisher_id == "mineducacion"


async def test_resolve_abbreviated_entity_via_alias(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(session, "MinTIC")

    assert resolution.status == "verified"
    assert resolution.official_publisher_id == "mintic"


async def test_resolve_ambiguous_alias_is_unknown(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(session, "Secretaria de Educacion")

    assert resolution.status == "unknown"
    assert resolution.reason == "publisher_alias_ambiguous"
    assert resolution.official_publisher_id is None


async def test_resolve_known_private_publisher(engine, loaded_fixture) -> None:
    fixture, _ = loaded_fixture

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(
            session,
            "Universidad de los Andes",
            known_private_publishers=fixture.known_private_publishers,
        )

    assert resolution.status == "private_or_non_official"
    assert resolution.reason == "publisher_private"


async def test_resolve_unrecognized_publisher_is_unknown(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        resolution = await resolve_publisher(session, "Entidad Totalmente Desconocida XYZ")

    assert resolution.status == "unknown"
    assert resolution.reason == "publisher_unknown"


async def test_duplicate_unambiguous_alias_violates_unique_index(engine, loaded_fixture) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(
            OfficialPublisherAlias(
                publisher_id="dane",
                alias_normalized="DANE",
                alias_raw="DANE duplicado",
                ambiguous=False,
                verification_source="prueba de duplicado",
                created_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
