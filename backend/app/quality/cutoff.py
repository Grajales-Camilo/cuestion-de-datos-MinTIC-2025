"""Inferencia de `data_cutoff_at` sobre las filas de una evidencia (T6, D3).

El corte estadistico se calcula SIEMPRE sobre las `rows` de la evidencia en
curso, nunca sobre `catalog_datasets.latest_observed_cutoff_at` (esa columna
es solo una pista de T2, contracts/validacion-calidad.md §1 y research.md
"Consecuencia" de la seccion de indice del catalogo). Si ninguna columna de
las filas es temporal/parseable, no hay `data_cutoff_at` y el llamador debe
usar el fallback `data_updated_at_fallback` (nunca lo hace este modulo).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

_YEAR_COLUMN_NAMES = {"a_o", "ano", "anio", "year", "vigencia"}
_DATE_COLUMN_HINTS = ("fecha", "periodo", "date")
_STRONG_KEYWORDS = ("corte", "final", "cierre", "actualizacion", "fin")
_STRONG_CONFIDENCE = 0.9
_WEAK_CONFIDENCE = 0.7

_YEAR_PATTERN = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class CutoffResult:
    data_cutoff_at: datetime
    method: str
    column: str
    confidence: float
    inferred_at: datetime


def _parse_temporal_value(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _YEAR_PATTERN.fullmatch(text):
        return date(int(text), 12, 31)
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _is_temporal_candidate_name(field_name: str) -> bool:
    name = field_name.lower()
    if name in _YEAR_COLUMN_NAMES:
        return True
    return any(hint in name for hint in _DATE_COLUMN_HINTS)


def infer_data_cutoff(
    rows: list[dict], evaluated_at: datetime
) -> CutoffResult | None:
    """Maximo valor del mejor campo temporal parseable presente en `rows`.

    Solo se considera candidata una columna cuyo NOMBRE sugiere temporalidad
    (`periodo`, `a_o`, `fecha_corte`... contracts/validacion-calidad.md §D3)
    Y cuyos valores son parseables en TODAS las filas (una columna que falla
    en una sola fila se descarta, no se usa un corte parcial).
    """
    if not rows:
        return None

    field_names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field_name in row:
            if field_name not in seen:
                seen.add(field_name)
                field_names.append(field_name)

    best: tuple[float, str, date] | None = None
    for field_name in field_names:
        if not _is_temporal_candidate_name(field_name):
            continue
        parsed_values: list[date] = []
        for row in rows:
            parsed = _parse_temporal_value(row.get(field_name))
            if parsed is None:
                parsed_values = []
                break
            parsed_values.append(parsed)
        if not parsed_values:
            continue

        confidence = (
            _STRONG_CONFIDENCE
            if any(keyword in field_name.lower() for keyword in _STRONG_KEYWORDS)
            else _WEAK_CONFIDENCE
        )
        candidate = (confidence, field_name, max(parsed_values))
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return None

    confidence, column, max_date = best
    return CutoffResult(
        data_cutoff_at=_combine_utc(max_date),
        method="max_temporal_column",
        column=column,
        confidence=confidence,
        inferred_at=evaluated_at,
    )


def _combine_utc(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)
