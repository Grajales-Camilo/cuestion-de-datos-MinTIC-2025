"""Clasificador determinista de riesgo PII para el catalogo (T-201, plan.md §5.3b).

Estrategia (Art. VI.1 de la constitucion): cualquier columna que no matchee
ningun patron de high/medium/low queda en `default_column_risk` ("unknown",
bloqueada) -- nunca "low" por omision.

Correccion verificada contra datos reales (hallazgo T-303, 2026-07-10): el
allowlist de `low` usa patrones anclados (`^...$`) pensados para comparar
contra el NOMBRE exacto de una columna. La implementacion original los
evaluaba contra el mismo haystack concatenado (`field_name + display_name +
description`) que high/medium; con una descripcion no vacia (el caso normal
en produccion) el ancla `$` nunca alcanza el final del nombre real y "low"
queda practicamente inalcanzable. Verificado contra el catalogo ya
ingerido: 0 de 2.611 datasets `api_active=true` + `publisher verified`
resultaban `pii_risk_level=low`. La correccion evalua el allowlist de `low`
SOLO contra `display_name` (preferido) o `field_name`, normalizados y sin
concatenar con `description`. Ademas Socrata reemplaza cada caracter
acentuado por `_` en `field_name` ("codigo" -> "c_digo", "deserci_n",
"a_o") pero preserva la tilde en `display_name`; preferir `display_name`
resuelve ese mangling sin heuristicas adicionales. `high`/`medium` NO
cambian: siguen escaneando el haystack completo (field_name+display_name+
description) igual que antes, preservando que una descripcion sospechosa
pueda escalar una columna de nombre generico
(`test_description_can_trigger_classification`). El cambio SOLO amplia
cuando una columna puede resolver a `low`; nunca puede degradar una columna
que ya calificaba como `high`/`medium` porque esos chequeos corren primero
y no se tocan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.db.publishers import normalize_publisher_name

DEFAULT_PII_FIXTURE_PATH = Path(__file__).resolve().parent / "pii_patterns.yaml"

_RISK_SEVERITY = {"low": 0, "medium": 1, "unknown": 2, "high": 3}


class PiiPattern(BaseModel):
    id: str
    pattern: str
    reason: str


class ReviewedDatasetColumns(BaseModel):
    """Clasificaciones acotadas a un esquema observado y una fuente auditable."""

    risk_level: str
    columns: set[str] = Field(default_factory=set)
    source: str
    reason: str
    override_medium: bool = False


class PiiPatternsFixture(BaseModel):
    fixture_version: str
    updated_at: datetime
    default_column_risk: str = "unknown"
    high_risk_column_patterns: list[PiiPattern] = Field(default_factory=list)
    medium_risk_column_patterns: list[PiiPattern] = Field(default_factory=list)
    low_risk_column_allowlist: list[PiiPattern] = Field(default_factory=list)
    dataset_level_keywords: dict[str, list[str]] = Field(default_factory=dict)
    reviewed_dataset_columns: dict[str, ReviewedDatasetColumns] = Field(default_factory=dict)


def load_pii_patterns(path: Path = DEFAULT_PII_FIXTURE_PATH) -> PiiPatternsFixture:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PiiPatternsFixture.model_validate(data)


@dataclass
class ColumnPiiClassification:
    risk_level: str
    matched_pattern_id: str | None = None


@dataclass
class DatasetPiiClassification:
    risk_level: str


def _normalized_haystack(*parts: str | None) -> str:
    return normalize_publisher_name(" ".join(part for part in parts if part))


def classify_column(
    field_name: str,
    display_name: str | None,
    description: str | None,
    fixture: PiiPatternsFixture,
    *,
    dataset_id: str | None = None,
) -> ColumnPiiClassification:
    haystack = _normalized_haystack(field_name, display_name, description)

    for pattern in fixture.high_risk_column_patterns:
        if re.search(pattern.pattern, haystack):
            return ColumnPiiClassification(risk_level="high", matched_pattern_id=pattern.id)
    reviewed = fixture.reviewed_dataset_columns.get(dataset_id or "")
    if (
        reviewed is not None
        and reviewed.override_medium
        and field_name in reviewed.columns
    ):
        return ColumnPiiClassification(
            risk_level=reviewed.risk_level,
            matched_pattern_id=f"reviewed_dataset:{dataset_id}",
        )
    for pattern in fixture.medium_risk_column_patterns:
        if re.search(pattern.pattern, haystack):
            return ColumnPiiClassification(risk_level="medium", matched_pattern_id=pattern.id)

    # Una revisión temática nunca rebaja señales high/medium y solo aplica a
    # nombres de columna exactos del esquema observado. Una columna nueva o
    # renombrada vuelve al default seguro `unknown`.
    if reviewed is not None and field_name in reviewed.columns:
        return ColumnPiiClassification(
            risk_level=reviewed.risk_level,
            matched_pattern_id=f"reviewed_dataset:{dataset_id}",
        )

    name_only = _normalized_haystack(display_name or field_name)
    for pattern in fixture.low_risk_column_allowlist:
        if re.search(pattern.pattern, name_only):
            return ColumnPiiClassification(risk_level="low", matched_pattern_id=pattern.id)
    return ColumnPiiClassification(risk_level=fixture.default_column_risk, matched_pattern_id=None)


def classify_dataset(
    columns: list[ColumnPiiClassification],
    name: str,
    description: str | None,
    category: str | None,
    fixture: PiiPatternsFixture,
) -> DatasetPiiClassification:
    """Riesgo del dataset = peor caso (MAX) de sus columnas, mas señales de
    titulo/descripcion/categoria (contracts/validacion-calidad.md linea 81:
    el chequeo de PII "unknown" mira dataset O columna seleccionada)."""

    if columns:
        worst = max(columns, key=lambda column: _RISK_SEVERITY[column.risk_level]).risk_level
    else:
        worst = "unknown"

    haystack = _normalized_haystack(name, description, category)
    for severity in ("high", "medium"):
        if _RISK_SEVERITY[severity] <= _RISK_SEVERITY[worst]:
            continue
        for keyword in fixture.dataset_level_keywords.get(severity, []):
            if re.search(keyword, haystack):
                worst = severity
                break

    return DatasetPiiClassification(risk_level=worst)
