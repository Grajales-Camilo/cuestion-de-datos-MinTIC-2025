"""Registro canonico de publicadores oficiales: fixture, carga y resolucion (T-106/T-201, RF-401).

`resolve_publisher()` acepta un `reference_date` opcional (T-201): sin el,
el comportamiento es identico al de T-106 (nombre canonico, alias unico,
alias ambiguo, publicador privado conocido). Con `reference_date`, aplica
ademas vigencia institucional y resolucion a sucesor (data-model.md:
"Entidades inactivas son elegibles solo si el dataset fue publicado dentro
de su vigencia... o si existe successor_id documentado").
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


def is_publisher_valid_for_reference_date(
    active: bool,
    valid_from: date | None,
    valid_until: date | None,
    reference_date: date,
) -> bool:
    """Vigencia institucional (data-model.md linea 75): "Entidades activas
    publican evidencia normal" (siempre validas); "Entidades inactivas son
    elegibles solo si el dataset fue publicado dentro de su vigencia"."""

    if active:
        return True
    if valid_from is not None and reference_date < valid_from:
        return False
    if valid_until is not None and reference_date > valid_until:
        return False
    return True


async def _resolve_publisher_id_with_vigencia(
    session: AsyncSession,
    publisher_id: str,
    reference_date: date,
    _depth: int = 0,
) -> PublisherResolution:
    if _depth > 5:
        return PublisherResolution(
            official_publisher_id=None, status="unknown", reason="publisher_unknown"
        )

    publisher = await session.get(OfficialPublisher, publisher_id)
    if publisher is None:
        return PublisherResolution(
            official_publisher_id=None, status="unknown", reason="publisher_unknown"
        )

    if is_publisher_valid_for_reference_date(
        publisher.active, publisher.valid_from, publisher.valid_until, reference_date
    ):
        return PublisherResolution(official_publisher_id=publisher.id, status="verified")

    if publisher.successor_id is not None:
        return await _resolve_publisher_id_with_vigencia(
            session, publisher.successor_id, reference_date, _depth + 1
        )

    return PublisherResolution(
        official_publisher_id=None, status="unknown", reason="publisher_unknown"
    )


async def resolve_publisher(
    session: AsyncSession,
    raw_publisher_text: str,
    known_private_publishers: list[PrivatePublisherFixture] | None = None,
    reference_date: date | None = None,
) -> PublisherResolution:
    """Resuelve texto crudo de publicador contra el registro oficial (RF-401).

    Sin `reference_date`, no decide vigencia institucional ni sucesor (T-106).
    Con `reference_date` (T-201), aplica vigencia y resuelve hacia el sucesor
    cuando el match historico ya no es valido en esa fecha.
    """

    normalized = normalize_publisher_name(raw_publisher_text)

    canonical_match = (
        await session.execute(
            select(OfficialPublisher).where(OfficialPublisher.normalized_name == normalized)
        )
    ).scalar_one_or_none()
    if canonical_match is not None:
        if reference_date is None:
            return PublisherResolution(official_publisher_id=canonical_match.id, status="verified")
        return await _resolve_publisher_id_with_vigencia(
            session, canonical_match.id, reference_date
        )

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
        if reference_date is None:
            return PublisherResolution(
                official_publisher_id=alias_rows[0].publisher_id, status="verified"
            )
        return await _resolve_publisher_id_with_vigencia(
            session, alias_rows[0].publisher_id, reference_date
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
