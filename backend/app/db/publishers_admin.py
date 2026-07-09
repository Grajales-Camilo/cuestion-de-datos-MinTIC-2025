"""Fusion en memoria de entidades nuevas sobre el fixture de publicadores
oficiales (T-201A, seguimiento operativo de research.md #7).

Modulo puro (sin I/O): recibe el dict ya cargado del fixture JSON y una
lista de filas de un CSV, y devuelve el dict modificado + un resumen.
`scripts/add_publishers.py` es el unico responsable de leer/escribir
archivos; aqui solo vive la logica que decide si una fila es una entidad
nueva, una ampliacion de una existente, o un conflicto que hay que
rechazar (id repetido, alias no ambiguo que ya pertenece a otra entidad,
canonical_name que colisiona con un alias existente).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.db.publishers import normalize_publisher_name

ALLOWED_ENTITY_TYPES = {
    "ministerio",
    "departamento_administrativo",
    "gobernacion",
    "alcaldia",
    "universidad_publica",
    "empresa_estado",
    "establecimiento_publico",
    "otra_estatal",
}
REQUIRED_CSV_COLUMNS = {"id", "canonical_name", "entity_type", "verification_source"}


class AddPublishersError(Exception):
    """Error de validacion del CSV o de consistencia con el fixture existente."""


@dataclass
class MergeSummary:
    publishers_added: int = 0
    publishers_updated: int = 0
    aliases_added: int = 0
    warnings: list[str] = field(default_factory=list)


def split_aliases(raw: str) -> list[str]:
    return [part.strip() for part in raw.split("|") if part.strip()]


def _build_alias_owner_index(publishers: list[dict]) -> dict[str, str]:
    """Mapa `texto normalizado -> id` de todo nombre canonico y alias no
    ambiguo ya presente en el fixture. Un alias no ambiguo nuevo que
    normalice igual a una entrada de este indice, bajo OTRO id, violaria
    el indice parcial unico `uq_official_alias_unambiguous` al recargar
    (data-model.md) -- se detecta aqui antes de escribir nada."""

    index: dict[str, str] = {}
    for publisher in publishers:
        index[normalize_publisher_name(publisher["canonical_name"])] = publisher["id"]
        for alias in publisher.get("aliases", []):
            if not alias.get("ambiguous", False):
                index[normalize_publisher_name(alias["alias_raw"])] = publisher["id"]
    return index


def merge_publishers(
    data: dict, rows: list[dict], *, update_existing: bool
) -> MergeSummary:
    """Aplica `rows` (una fila por publicador nuevo o ampliado) sobre
    `data` (el dict ya cargado del fixture JSON), en memoria. Lanza
    `AddPublishersError` ante cualquier inconsistencia -- no deja el
    fixture a medio modificar; el llamador solo persiste si esta funcion
    retorna sin excepcion."""

    summary = MergeSummary()
    publishers_by_id = {p["id"]: p for p in data["publishers"]}
    alias_owner = _build_alias_owner_index(data["publishers"])
    seen_ids_in_batch: set[str] = set()

    for line_number, row in enumerate(rows, start=2):  # 1 = encabezado
        publisher_id = (row.get("id") or "").strip()
        canonical_name = (row.get("canonical_name") or "").strip()
        entity_type = (row.get("entity_type") or "").strip()
        verification_source = (row.get("verification_source") or "").strip()
        active_raw = (row.get("active") or "true").strip().lower()

        if not publisher_id or not canonical_name or not entity_type or not verification_source:
            raise AddPublishersError(
                f"fila {line_number}: id/canonical_name/entity_type/verification_source "
                "no pueden estar vacios."
            )
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise AddPublishersError(
                f"fila {line_number} ({publisher_id}): entity_type '{entity_type}' invalido. "
                f"Permitidos: {sorted(ALLOWED_ENTITY_TYPES)}."
            )
        if active_raw not in {"true", "false"}:
            raise AddPublishersError(
                f"fila {line_number} ({publisher_id}): active debe ser 'true' o 'false'."
            )
        if publisher_id in seen_ids_in_batch:
            raise AddPublishersError(f"id duplicado dentro del CSV: {publisher_id!r}.")
        seen_ids_in_batch.add(publisher_id)

        aliases = [
            {"alias_raw": raw, "ambiguous": False, "verification_source": verification_source}
            for raw in split_aliases(row.get("aliases") or "")
        ]
        aliases += [
            {"alias_raw": raw, "ambiguous": True, "verification_source": verification_source}
            for raw in split_aliases(row.get("ambiguous_aliases") or "")
        ]

        for alias in aliases:
            if alias["ambiguous"]:
                continue
            normalized = normalize_publisher_name(alias["alias_raw"])
            owner = alias_owner.get(normalized)
            if owner is not None and owner != publisher_id:
                raise AddPublishersError(
                    f"fila {line_number} ({publisher_id}): el alias {alias['alias_raw']!r} ya "
                    f"pertenece a {owner!r} como termino no ambiguo. Marcalo en "
                    "ambiguous_aliases o corrige el texto."
                )

        existing = publishers_by_id.get(publisher_id)
        if existing is None:
            normalized_canonical = normalize_publisher_name(canonical_name)
            owner = alias_owner.get(normalized_canonical)
            if owner is not None and owner != publisher_id:
                raise AddPublishersError(
                    f"fila {line_number} ({publisher_id}): canonical_name normaliza igual que "
                    f"un nombre/alias ya registrado en {owner!r}."
                )
            new_entry = {
                "id": publisher_id,
                "canonical_name": canonical_name,
                "entity_type": entity_type,
                "active": active_raw == "true",
                "verification_source": verification_source,
                "aliases": aliases,
            }
            data["publishers"].append(new_entry)
            publishers_by_id[publisher_id] = new_entry
            alias_owner[normalized_canonical] = publisher_id
            for alias in aliases:
                if not alias["ambiguous"]:
                    alias_owner[normalize_publisher_name(alias["alias_raw"])] = publisher_id
            summary.publishers_added += 1
            summary.aliases_added += len(aliases)
            continue

        # id ya existe: ampliar, no reemplazar en silencio.
        changed_fields = {
            field_name: value
            for field_name, value in (
                ("canonical_name", canonical_name),
                ("entity_type", entity_type),
                ("verification_source", verification_source),
                ("active", active_raw == "true"),
            )
            if existing.get(field_name) != value
        }
        if changed_fields and not update_existing:
            raise AddPublishersError(
                f"fila {line_number} ({publisher_id}): ya existe con otros valores "
                f"{changed_fields}; usa --update-existing si la intencion es corregirlo."
            )
        if changed_fields and update_existing:
            existing.update(changed_fields)
            summary.publishers_updated += 1
            summary.warnings.append(f"{publisher_id}: actualizado {sorted(changed_fields)}")

        existing_alias_texts = {
            normalize_publisher_name(alias["alias_raw"]) for alias in existing.get("aliases", [])
        }
        added_here = 0
        for alias in aliases:
            normalized = normalize_publisher_name(alias["alias_raw"])
            if normalized in existing_alias_texts:
                summary.warnings.append(
                    f"{publisher_id}: alias {alias['alias_raw']!r} ya existia, se omite."
                )
                continue
            existing.setdefault("aliases", []).append(alias)
            existing_alias_texts.add(normalized)
            if not alias["ambiguous"]:
                alias_owner[normalized] = publisher_id
            added_here += 1
        summary.aliases_added += added_here

    return summary
