"""T3 `resolver_geografia` (contracts/agent-tools.md §T3, RF-202, ESC-01).

Resuelve nombres de lugares a `divipola_entries` (T-202) con dos señales
combinadas: similitud trigram (`pg_trgm`) sobre `name_normalized` para
variantes de tildes/mayusculas, y coincidencia exacta contra `alt_names`
(normalizado en Python, sin extension `unaccent` disponible en la base -- ver
db/init/01_extensions.sql) para variantes historicas/no derivables por
trigram (p. ej. "Bogotá" / "Santafé de Bogotá" para el codigo 11001,
sin superposicion de trigramas entre si).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.divipola import normalize_name
from app.tools.errors import validation_error_envelope

MAX_MATCHES = 3
ALT_NAME_CONFIDENCE = 0.95
_ACCENTABLE_VOWELS = set("AEIOUÁÉÍÓÚ")


class ResolverGeografiaInput(BaseModel):
    termino: str = Field(min_length=2, max_length=200)


def build_like_pattern(name: str) -> str:
    """Vocales acentuables -> `_` (comodin SQL de un caracter); ver contrato §T3."""

    chars = ["_" if ch in _ACCENTABLE_VOWELS else ch for ch in name.upper()]
    return "%" + "".join(chars) + "%"


def _match_dict(row, confidence: float) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "department_code": row.department_code,
        "department_name": row.department_name,
        "level": row.level,
        "like_pattern": build_like_pattern(row.name),
        "confidence": round(confidence, 2),
    }


def rank_matches(trigram_rows: list, alt_rows: list, normalized_term: str) -> list[dict]:
    """Combina candidatos trigram (con `.score`) y `alt_names` (Python, sin DB).

    Funcion pura -- recibe filas ya obtenidas (SQLAlchemy `Row` o cualquier
    objeto con los mismos atributos) para poder probarse sin Postgres real.
    """
    candidates: dict[str, tuple[float, object]] = {}
    for row in trigram_rows:
        candidates[row.code] = (float(row.score), row)
    for row in alt_rows:
        if any(normalize_name(alt) == normalized_term for alt in row.alt_names or []):
            existing = candidates.get(row.code)
            if existing is None or ALT_NAME_CONFIDENCE > existing[0]:
                candidates[row.code] = (ALT_NAME_CONFIDENCE, row)

    ordered = sorted(candidates.values(), key=lambda pair: -pair[0])[:MAX_MATCHES]
    return [_match_dict(row, confidence) for confidence, row in ordered]


async def resolver_geografia(raw_input: dict, *, engine: AsyncEngine) -> dict:
    try:
        parsed_input = ResolverGeografiaInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    normalized_term = normalize_name(parsed_input.termino)

    async with engine.connect() as connection:
        trigram_rows = (
            await connection.execute(
                text(
                    """
                    SELECT code, name, department_code, department_name, level,
                           similarity(name_normalized, :term) AS score
                    FROM divipola_entries
                    WHERE name_normalized % :term
                    ORDER BY score DESC
                    LIMIT 10
                    """
                ),
                {"term": normalized_term},
            )
        ).all()
        alt_rows = (
            await connection.execute(
                text(
                    "SELECT code, name, department_code, department_name, level, alt_names "
                    "FROM divipola_entries WHERE alt_names IS NOT NULL"
                )
            )
        ).all()

    matches = rank_matches(trigram_rows, alt_rows, normalized_term)
    return {"ok": True, "matches": matches}
