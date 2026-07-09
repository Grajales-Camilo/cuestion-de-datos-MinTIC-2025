"""Maestro DIVIPOLA: normalizacion y upsert idempotente (T-202, data-model.md #6).

Fuente confirmada en el portal (2026-07-08): dataset SODA `gdxc-w37w`,
"DIVIPOLA- Codigos municipios" (DANE, licencia CC BY-SA 4.0), 1122 filas,
columnas `cod_dpto`/`dpto`/`cod_mpio`/`nom_mpio`/`tipo_municipio`/`longitud`/
`latitud`. El recurso solo lista municipios (incluye "Isla" y "Area no
municipalizada" bajo el mismo nivel administrativo de 5 digitos); las
entradas `level="department"` se derivan agrupando los pares
`(cod_dpto, dpto)` unicos que ya traen esas mismas filas, porque el DANE no
publica en este id un recurso separado de departamentos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import DivipolaEntry


def normalize_name(raw: str) -> str:
    """Sin tildes, mayusculas, espacios colapsados (data-model.md: name_normalized)."""

    decomposed = unicodedata.normalize("NFKD", raw.strip())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_accents)
    return collapsed.upper()


# Alias comunes documentados (data-model.md #6, ejemplo literal "Bogota D.C.",
# "Santafe de Bogota"). Lista deliberadamente pequeña: son variantes
# textuales de nombres ya confirmados en la fuente (no inventa relaciones ni
# cifras, Constitucion Art. I), agregadas solo para los casos donde el
# nombre oficial DANE difiere notablemente del uso corriente.
KNOWN_ALT_NAMES: dict[str, list[str]] = {
    "11001": ["Bogotá", "Bogotá D.C.", "Santafé de Bogotá"],
    "11": ["Bogotá", "Bogotá D.C.", "Santafé de Bogotá"],
}


class DivipolaRowError(ValueError):
    """Fila fuente sin los campos minimos requeridos (cod_mpio/nom_mpio/cod_dpto/dpto)."""


@dataclass
class DivipolaEntryData:
    code: str
    name: str
    department_code: str | None
    department_name: str | None
    level: str
    name_normalized: str
    alt_names: list[str] | None


def municipality_entry_from_row(row: dict) -> DivipolaEntryData:
    code = str(row.get("cod_mpio") or "").strip()
    name = str(row.get("nom_mpio") or "").strip()
    department_code = str(row.get("cod_dpto") or "").strip()
    department_name = str(row.get("dpto") or "").strip()
    if not code or not name or not department_code or not department_name:
        raise DivipolaRowError(f"fila DIVIPOLA incompleta: {row!r}")

    return DivipolaEntryData(
        code=code,
        name=name,
        department_code=department_code,
        department_name=department_name,
        level="municipality",
        name_normalized=normalize_name(name),
        alt_names=KNOWN_ALT_NAMES.get(code),
    )


def derive_department_entries(
    municipalities: list[DivipolaEntryData],
) -> list[DivipolaEntryData]:
    """Agrupa los `(department_code, department_name)` unicos de las filas de
    municipio en entradas `level="department"` (el recurso fuente no trae un
    listado separado de departamentos)."""

    seen: dict[str, DivipolaEntryData] = {}
    for muni in municipalities:
        code = muni.department_code
        if not code or code in seen:
            continue
        name = muni.department_name or ""
        seen[code] = DivipolaEntryData(
            code=code,
            name=name,
            department_code=None,
            department_name=None,
            level="department",
            name_normalized=normalize_name(name),
            alt_names=KNOWN_ALT_NAMES.get(code),
        )
    return list(seen.values())


def rows_to_entries(rows: list[dict]) -> list[DivipolaEntryData]:
    """Convierte filas crudas SODA en entradas `divipola_entries`
    (departamentos derivados + municipios), listas para `upsert_divipola_entries`."""

    municipalities = [municipality_entry_from_row(row) for row in rows]
    departments = derive_department_entries(municipalities)
    return departments + municipalities


@dataclass
class DivipolaLoadSummary:
    entries_created: int = 0
    entries_updated: int = 0


async def upsert_divipola_entries(
    engine: AsyncEngine, entries: list[DivipolaEntryData]
) -> DivipolaLoadSummary:
    """Upsert idempotente por `code` (PK) -- re-ejecutar no duplica filas (T-202)."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    summary = DivipolaLoadSummary()
    codes = [entry.code for entry in entries]

    async with session_factory() as session, session.begin():
        existing_codes = set(
            (
                await session.execute(
                    select(DivipolaEntry.code).where(DivipolaEntry.code.in_(codes))
                )
            ).scalars()
        )

        for entry in entries:
            stmt = pg_insert(DivipolaEntry).values(
                code=entry.code,
                name=entry.name,
                department_code=entry.department_code,
                department_name=entry.department_name,
                level=entry.level,
                name_normalized=entry.name_normalized,
                alt_names=entry.alt_names,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[DivipolaEntry.code],
                set_={
                    "name": stmt.excluded.name,
                    "department_code": stmt.excluded.department_code,
                    "department_name": stmt.excluded.department_name,
                    "level": stmt.excluded.level,
                    "name_normalized": stmt.excluded.name_normalized,
                    "alt_names": stmt.excluded.alt_names,
                },
            )
            await session.execute(stmt)
            if entry.code in existing_codes:
                summary.entries_updated += 1
            else:
                summary.entries_created += 1

    return summary
