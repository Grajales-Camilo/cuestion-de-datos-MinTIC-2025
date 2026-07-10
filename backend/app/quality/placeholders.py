"""Deteccion CONTEXTUAL de placeholders para D2 (T-401, contracts/validacion-calidad.md).

Nunca una lista universal: un valor solo se marca como placeholder si
cumple al menos una de las tres reglas del contrato:
(a) coincide con un patron generico configurado en `placeholders.yaml` Y
    supera `PLACEHOLDER_MIN_RATIO` de las celdas citadas;
(b) el codebook de esa columna (provisto por el llamador, no inventado
    aqui) declara ese codigo como "no aplica/no responde" -- cualquier
    ocurrencia cuenta, sin importar la proporcion;
(c) esta cubierto por (a) con los patrones genericos de "Default …",
    "NO ESPECIFICA", "-1", etc.

Por diseño, valores como `9`/`99` NUNCA se marcan por (a) -- no hay patron
generico para digitos sueltos -- solo por (b), evitando falsos positivos
sobre columnas donde esos numeros son datos reales (pruebas.md §2.1, caso 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_PLACEHOLDERS_FIXTURE_PATH = Path(__file__).resolve().parent / "placeholders.yaml"


class PlaceholderPattern(BaseModel):
    id: str
    pattern: str
    reason: str


class PlaceholdersFixture(BaseModel):
    fixture_version: str
    updated_at: datetime
    generic_candidate_patterns: list[PlaceholderPattern] = Field(default_factory=list)


def load_placeholder_patterns(
    path: Path = DEFAULT_PLACEHOLDERS_FIXTURE_PATH,
) -> PlaceholdersFixture:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PlaceholdersFixture.model_validate(data)


@dataclass(frozen=True)
class PlaceholderDetection:
    column: str
    value: str
    reason: str
    ratio: float


@dataclass(frozen=True)
class ColumnValues:
    field_name: str
    values: tuple[object, ...]
    known_placeholder_codes: tuple[str, ...] = field(default_factory=tuple)


def _value_counts(values: tuple[object, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    return counts


def detect_placeholder(
    column: ColumnValues,
    fixture: PlaceholdersFixture,
    min_ratio: float,
) -> PlaceholderDetection | None:
    total = len(column.values)
    if total == 0:
        return None
    counts = _value_counts(column.values)

    for value, count in counts.items():
        ratio = count / total
        if value in column.known_placeholder_codes:
            return PlaceholderDetection(
                column=column.field_name,
                value=value,
                reason=(
                    f"'{value}' esta documentado como codigo de 'no aplica/no responde' "
                    "para esta columna"
                ),
                ratio=ratio,
            )

    for value, count in counts.items():
        ratio = count / total
        for pattern in fixture.generic_candidate_patterns:
            if re.search(pattern.pattern, value) and ratio >= min_ratio:
                return PlaceholderDetection(
                    column=column.field_name, value=value, reason=pattern.reason, ratio=ratio
                )

    return None


def detect_placeholders(
    columns: list[ColumnValues], fixture: PlaceholdersFixture, min_ratio: float
) -> list[PlaceholderDetection]:
    detections = []
    for column in columns:
        detection = detect_placeholder(column, fixture, min_ratio)
        if detection is not None:
            detections.append(detection)
    return detections
