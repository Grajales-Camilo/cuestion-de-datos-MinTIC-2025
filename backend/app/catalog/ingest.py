"""Orquestador de ingesta del catalogo (T-201, RF-701, RF-304, plan.md §5).

Cada item se procesa en su propia transaccion: si uno falla (registro
malformado, error de resolucion), no debe "envenenar" la transaccion de los
demas items de la misma pagina -- por eso NO se comparte una unica
transaccion por pagina.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.discovery_client import DiscoveryClient
from app.catalog.normalize import to_normalized_dataset
from app.catalog.upsert import (
    ColumnUpsertData,
    DatasetUpsertData,
    reset_api_active_flags,
    upsert_dataset,
)
from app.config import Settings
from app.db.models import IngestRun
from app.db.publishers import OfficialPublishersFixture, load_fixture, resolve_publisher
from app.quality.eligibility import compute_column_eligibility, compute_dataset_eligibility
from app.quality.pii_classifier import (
    PiiPatternsFixture,
    classify_column,
    classify_dataset,
    load_pii_patterns,
)

_MAX_ERROR_SUMMARY_ENTRIES = 50
_ERROR_MESSAGE_MAX_CHARS = 300
_INHERITED_COLUMN_REASONS = {"api_inactive", "publisher_unknown", "publisher_private"}
_DISCOVERY_BASE_URL = "https://api.us.socrata.com"


@dataclass
class IngestRunSummary:
    ingest_run_id: str | None = None
    datasets_new: int = 0
    datasets_updated: int = 0
    datasets_failed: int = 0
    error_summary: list[dict] = field(default_factory=list)


def _record_error(summary: IngestRunSummary, dataset_id: str, message: str) -> None:
    if len(summary.error_summary) >= _MAX_ERROR_SUMMARY_ENTRIES:
        return
    summary.error_summary.append(
        {"dataset_id": dataset_id, "error": message[:_ERROR_MESSAGE_MAX_CHARS]}
    )


async def _process_item(
    session: AsyncSession,
    item: dict,
    publishers_fixture: OfficialPublishersFixture,
    pii_fixture: PiiPatternsFixture,
) -> str | None:
    """Procesa un item de Discovery API. Devuelve "created"/"updated", o
    `None` si el item se descarta por filtro (no tabular/sin nombre) --
    descartar no es un fallo."""

    normalized = to_normalized_dataset(item)
    if normalized is None:
        return None

    reference_date = normalized.data_updated_at.date() if normalized.data_updated_at else None
    publisher_resolution = await resolve_publisher(
        session,
        normalized.publisher_text or "",
        known_private_publishers=publishers_fixture.known_private_publishers,
        reference_date=reference_date,
    )

    column_classifications = [
        classify_column(column.field_name, column.display_name, column.description, pii_fixture)
        for column in normalized.columns
    ]
    dataset_pii = classify_dataset(
        column_classifications,
        normalized.name,
        normalized.description,
        normalized.category,
        pii_fixture,
    )

    dataset_eligibility = compute_dataset_eligibility(
        publisher_status=publisher_resolution.status,
        pii_risk_level=dataset_pii.risk_level,
        api_active=True,
    )
    inherited_column_reasons = [
        reason
        for reason in dataset_eligibility.eligibility_reasons
        if reason in _INHERITED_COLUMN_REASONS
    ]

    columns_upsert = []
    for column, column_pii in zip(normalized.columns, column_classifications, strict=True):
        column_eligibility = compute_column_eligibility(
            inherited_column_reasons, column_pii.risk_level
        )
        columns_upsert.append(
            ColumnUpsertData(
                field_name=column.field_name,
                display_name=column.display_name,
                data_type=column.data_type,
                description=column.description,
                pii_risk_level=column_pii.risk_level,
                eligibility_status=column_eligibility.eligibility_status,
                eligibility_reasons=column_eligibility.eligibility_reasons,
            )
        )

    dataset_data = DatasetUpsertData(
        id=normalized.id,
        name=normalized.name,
        description=normalized.description,
        publisher_text=normalized.publisher_text,
        official_publisher_id=publisher_resolution.official_publisher_id,
        publisher_verification_status=publisher_resolution.status,
        category=normalized.category,
        data_updated_at=normalized.data_updated_at,
        metadata_synced_at=datetime.now(UTC),
        embedding_text=normalized.embedding_text,
        pii_risk_level=dataset_pii.risk_level,
        eligibility_status=dataset_eligibility.eligibility_status,
        eligibility_reasons=dataset_eligibility.eligibility_reasons,
        columns=columns_upsert,
    )

    return await upsert_dataset(session, dataset_data)


async def run_ingest(
    engine: AsyncEngine,
    settings: Settings,
    trigger: Literal["manual", "cron"] = "manual",
    limit: int | None = None,
    page_size: int = 1000,
    domain: str = "www.datos.gov.co",
) -> IngestRunSummary:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    summary = IngestRunSummary()
    pii_fixture = load_pii_patterns()
    publishers_fixture = load_fixture()

    async with session_factory() as session, session.begin():
        run = IngestRun(started_at=datetime.now(UTC), trigger=trigger)
        session.add(run)
    summary.ingest_run_id = str(run.id)

    try:
        if limit is None:
            async with session_factory() as session, session.begin():
                await reset_api_active_flags(session)

        app_token = (
            settings.socrata_app_token.get_secret_value() if settings.socrata_app_token else None
        )
        processed = 0
        async with httpx.AsyncClient(base_url=_DISCOVERY_BASE_URL) as http_client:
            discovery = DiscoveryClient(http_client, app_token=app_token)

            async for page in discovery.iter_pages(domain=domain, page_size=page_size):
                for item in page:
                    if limit is not None and processed >= limit:
                        break
                    dataset_id = (item.get("resource") or {}).get("id", "desconocido")
                    try:
                        async with session_factory() as session, session.begin():
                            outcome = await _process_item(
                                session, item, publishers_fixture, pii_fixture
                            )
                    except Exception as exc:  # noqa: BLE001 - registrar y continuar con el resto
                        summary.datasets_failed += 1
                        _record_error(summary, dataset_id, str(exc))
                    else:
                        if outcome == "created":
                            summary.datasets_new += 1
                        elif outcome == "updated":
                            summary.datasets_updated += 1
                    processed += 1
                if limit is not None and processed >= limit:
                    break
    except Exception as exc:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(IngestRun)
                .where(IngestRun.id == run.id)
                .values(
                    finished_at=datetime.now(UTC),
                    error_summary=[{"fatal": str(exc)[:_ERROR_MESSAGE_MAX_CHARS]}],
                )
            )
        raise

    async with session_factory() as session, session.begin():
        await session.execute(
            update(IngestRun)
            .where(IngestRun.id == run.id)
            .values(
                finished_at=datetime.now(UTC),
                datasets_new=summary.datasets_new,
                datasets_updated=summary.datasets_updated,
                datasets_failed=summary.datasets_failed,
                error_summary=summary.error_summary,
            )
        )

    return summary
