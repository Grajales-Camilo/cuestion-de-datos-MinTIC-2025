"""Registro canonico de publicadores oficiales: fixture, carga y resolucion (T-106, RF-401).

La resolucion aqui cubre solo lo que T-106 puede probar sin datasets reales
(nombre canonico, alias unico, alias ambiguo, publicador privado conocido).
T-201 extiende la resolucion con vigencia institucional y sucesor usando la
fecha de publicacion del dataset, que no existe todavia en este alcance.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import OfficialPublisher, OfficialPublisherAlias

DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "official_publishers.json"


def normalize_publisher_name(raw: str) -> str:
    """Normaliza: trim, mayusculas, sin tildes, espacios colapsados (data-model.md)."""

    decomposed = unicodedata.normalize("NFKD", raw.strip())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_accents)
    return collapsed.upper()


class AliasFixture(BaseModel):
    alias_raw: str
    ambiguous: bool = False
    verification_source: str


class PublisherFixture(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    active: bool = True
    valid_from: date | None = None
    valid_until: date | None = None
    successor_id: str | None = None
    verification_source: str
    aliases: list[AliasFixture] = Field(default_factory=list)


class PrivatePublisherFixture(BaseModel):
    name_raw: str
    verification_source: str
    note: str | None = None


class OfficialPublishersFixture(BaseModel):
    fixture_version: str
    updated_at: datetime
    publishers: list[PublisherFixture]
    known_private_publishers: list[PrivatePublisherFixture] = Field(default_factory=list)


def load_fixture(path: Path = DEFAULT_FIXTURE_PATH) -> OfficialPublishersFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    return OfficialPublishersFixture.model_validate(data)


@dataclass
class ReloadSummary:
    publishers_created: int = 0
    publishers_updated: int = 0
    aliases_created: int = 0
    ambiguous_aliases: int = 0


async def reload_official_publishers(
    engine: AsyncEngine, fixture: OfficialPublishersFixture
) -> ReloadSummary:
    """Upsert idempotente de publicadores y reemplazo de sus alias (RF-401)."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    summary = ReloadSummary()
    fixture_ids = [publisher.id for publisher in fixture.publishers]

    async with session_factory() as session, session.begin():
        existing_ids = set(
            (
                await session.execute(
                    select(OfficialPublisher.id).where(OfficialPublisher.id.in_(fixture_ids))
                )
            ).scalars()
        )

        for publisher in fixture.publishers:
            stmt = pg_insert(OfficialPublisher).values(
                id=publisher.id,
                canonical_name=publisher.canonical_name,
                normalized_name=normalize_publisher_name(publisher.canonical_name),
                entity_type=publisher.entity_type,
                active=publisher.active,
                valid_from=publisher.valid_from,
                valid_until=publisher.valid_until,
                successor_id=None,
                verification_source=publisher.verification_source,
                updated_at=fixture.updated_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[OfficialPublisher.id],
                set_={
                    "canonical_name": stmt.excluded.canonical_name,
                    "normalized_name": stmt.excluded.normalized_name,
                    "entity_type": stmt.excluded.entity_type,
                    "active": stmt.excluded.active,
                    "valid_from": stmt.excluded.valid_from,
                    "valid_until": stmt.excluded.valid_until,
                    "verification_source": stmt.excluded.verification_source,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            if publisher.id in existing_ids:
                summary.publishers_updated += 1
            else:
                summary.publishers_created += 1

        # Segunda pasada: resolver successor_id una vez existen todas las filas.
        for publisher in fixture.publishers:
            if publisher.successor_id is not None:
                await session.execute(
                    update(OfficialPublisher)
                    .where(OfficialPublisher.id == publisher.id)
                    .values(successor_id=publisher.successor_id)
                )

        await session.execute(
            delete(OfficialPublisherAlias).where(
                OfficialPublisherAlias.publisher_id.in_(fixture_ids)
            )
        )
        for publisher in fixture.publishers:
            for alias in publisher.aliases:
                session.add(
                    OfficialPublisherAlias(
                        publisher_id=publisher.id,
                        alias_normalized=normalize_publisher_name(alias.alias_raw),
                        alias_raw=alias.alias_raw,
                        ambiguous=alias.ambiguous,
                        verification_source=alias.verification_source,
                        created_at=fixture.updated_at,
                    )
                )
                summary.aliases_created += 1
                if alias.ambiguous:
                    summary.ambiguous_aliases += 1

    return summary


@dataclass
class PublisherResolution:
    official_publisher_id: str | None
    status: str
    reason: str | None = field(default=None)


async def resolve_publisher(
    session: AsyncSession,
    raw_publisher_text: str,
    known_private_publishers: list[PrivatePublisherFixture] | None = None,
) -> PublisherResolution:
    """Resuelve texto crudo de publicador contra el registro oficial (RF-401).

    No decide vigencia institucional ni sucesor: eso depende de la fecha de
    publicacion del dataset y lo implementa T-201.
    """

    normalized = normalize_publisher_name(raw_publisher_text)

    canonical_match = (
        await session.execute(
            select(OfficialPublisher).where(OfficialPublisher.normalized_name == normalized)
        )
    ).scalar_one_or_none()
    if canonical_match is not None:
        return PublisherResolution(official_publisher_id=canonical_match.id, status="verified")

    alias_rows = (
        (
            await session.execute(
                select(OfficialPublisherAlias).where(
                    OfficialPublisherAlias.alias_normalized == normalized
                )
            )
        )
        .scalars()
        .all()
    )
    if len(alias_rows) == 1 and not alias_rows[0].ambiguous:
        return PublisherResolution(
            official_publisher_id=alias_rows[0].publisher_id, status="verified"
        )
    if alias_rows:
        return PublisherResolution(
            official_publisher_id=None,
            status="unknown",
            reason="publisher_alias_ambiguous",
        )

    if known_private_publishers:
        private_normalized = {
            normalize_publisher_name(entry.name_raw) for entry in known_private_publishers
        }
        if normalized in private_normalized:
            return PublisherResolution(
                official_publisher_id=None,
                status="private_or_non_official",
                reason="publisher_private",
            )

    return PublisherResolution(
        official_publisher_id=None, status="unknown", reason="publisher_unknown"
    )
