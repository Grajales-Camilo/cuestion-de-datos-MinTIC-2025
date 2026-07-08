"""Normalizacion de items de la Discovery API (T-201, plan.md §5.2-5.4).

Campos reales confirmados con peticiones en vivo contra la Discovery API
(no coinciden literalmente con los nombres que usa plan.md §5.3):
`resource.data_updated_at` (no `rowsUpdatedAt`); el publicador vive en
`owner.display_name` (no en `classification.domain_metadata`).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import zip_longest

_DESCRIPTION_MAX_CHARS = 2000
_EMBEDDING_TEXT_MAX_CHARS = 4000
_SHORT_DESCRIPTION_THRESHOLD = 100

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class NormalizedColumn:
    field_name: str
    display_name: str | None
    data_type: str
    description: str | None


@dataclass
class NormalizedDataset:
    id: str
    name: str
    description: str | None
    publisher_text: str | None
    category: str | None
    data_updated_at: datetime | None
    columns: list[NormalizedColumn] = field(default_factory=list)
    embedding_text: str = ""


def is_tabular_with_active_api(resource: dict) -> bool:
    """`type == "dataset"` (recursos map/file/href no traen columnas propias,
    confirmado con peticiones reales: un `type=map` trae `columns_field_name`
    vacio) y al menos una columna real."""

    return resource.get("type") == "dataset" and bool(resource.get("columns_field_name"))


def clean_description_html(raw: str | None) -> str | None:
    if raw is None:
        return None
    without_tags = _HTML_TAG_RE.sub(" ", raw)
    unescaped = html.unescape(without_tags)
    collapsed = _WHITESPACE_RE.sub(" ", unescaped).strip()
    return collapsed or None


def truncate_description(
    cleaned: str | None, max_chars: int = _DESCRIPTION_MAX_CHARS
) -> str | None:
    if cleaned is None:
        return None
    return cleaned[:max_chars]


def extract_columns(resource: dict) -> list[NormalizedColumn]:
    names = resource.get("columns_name") or []
    field_names = resource.get("columns_field_name") or []
    data_types = resource.get("columns_datatype") or []
    descriptions = resource.get("columns_description") or []

    columns: list[NormalizedColumn] = []
    for name, field_name, data_type, description in zip_longest(
        names, field_names, data_types, descriptions, fillvalue=None
    ):
        if not field_name:
            continue
        columns.append(
            NormalizedColumn(
                field_name=field_name,
                display_name=name or None,
                data_type=data_type or "text",
                description=description or None,
            )
        )
    return columns


def extract_publisher_text(item: dict) -> str | None:
    owner_name = (item.get("owner") or {}).get("display_name")
    if owner_name:
        return owner_name
    attribution = (item.get("resource") or {}).get("attribution")
    return attribution or None


def parse_data_updated_at(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(raw, tz=UTC)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def build_embedding_text(
    name: str,
    description: str | None,
    publisher_text: str | None,
    category: str | None,
    column_names: list[str],
) -> str:
    """plan.md §4: titulo + descripcion + entidad + categoria + columnas; si
    la descripcion es corta (< 100 chars), se pesa mas titulo y columnas."""

    description_text = description or ""
    columns_text = ", ".join(column_names)
    parts = [
        name if len(description_text) >= _SHORT_DESCRIPTION_THRESHOLD else f"{name}\n{name}",
        "",
        description_text,
        "",
        f"Entidad: {publisher_text or 'desconocida'}",
        f"Categoria: {category or 'sin categoria'}",
        f"Columnas: {columns_text}",
    ]
    if len(description_text) < _SHORT_DESCRIPTION_THRESHOLD:
        parts.append(f"Columnas relevantes: {columns_text}")

    return "\n".join(parts)[:_EMBEDDING_TEXT_MAX_CHARS]


def to_normalized_dataset(item: dict) -> NormalizedDataset | None:
    resource = item.get("resource") or {}
    if not is_tabular_with_active_api(resource):
        return None

    name = resource.get("name")
    if not name:
        return None

    dataset_id = resource.get("id")
    if not dataset_id:
        return None

    description = truncate_description(clean_description_html(resource.get("description")))
    publisher_text = extract_publisher_text(item)
    category = (item.get("classification") or {}).get("domain_category")
    columns = extract_columns(resource)

    return NormalizedDataset(
        id=dataset_id,
        name=name,
        description=description,
        publisher_text=publisher_text,
        category=category,
        data_updated_at=parse_data_updated_at(resource.get("data_updated_at")),
        columns=columns,
        embedding_text=build_embedding_text(
            name=name,
            description=description,
            publisher_text=publisher_text,
            category=category,
            column_names=[column.field_name for column in columns],
        ),
    )
