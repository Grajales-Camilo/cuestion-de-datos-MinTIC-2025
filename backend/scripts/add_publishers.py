"""CLI para ampliar el fixture de publicadores oficiales desde un CSV (T-201A).

Automatiza el paso mecanico que T-201A hizo a mano (fusionar entidades nuevas
en `backend/data/official_publishers.json` sin romper ids/aliases existentes).
NO reemplaza la verificacion humana de la fuente: cada fila del CSV debe traer
un `verification_source` real ya comprobado (pagina institucional, directorio
oficial, etc.) siguiendo la misma disciplina de T-106 -- este script valida
forma y consistencia, no procedencia. La logica de fusion vive en
`app/db/publishers_admin.py` (probada en `tests/test_add_publishers.py`).

Uso (desde backend/, ver quickstart.md §3):
    python scripts/add_publishers.py --input data/nuevos_publicadores.csv
    python scripts/add_publishers.py --input ruta.csv --dry-run
    python scripts/add_publishers.py --input ruta.csv --update-existing

Formato del CSV (encabezado obligatorio, UTF-8):
    id,canonical_name,entity_type,verification_source,aliases,ambiguous_aliases,active

- id: identificador estable en minusculas-con-guiones (p. ej. gobernacion-narino).
- canonical_name: nombre oficial completo.
- entity_type: uno de ministerio, departamento_administrativo, gobernacion,
  alcaldia, universidad_publica, empresa_estado, establecimiento_publico,
  otra_estatal (el mismo CHECK de `official_publishers`).
- verification_source: URL o referencia real ya verificada por un humano.
- aliases: opcional, texto(s) crudo(s) EXACTOS observados en
  `catalog_datasets.publisher` que no coincidan con `canonical_name` tras
  normalizar (mayusculas/sin tildes/espacios colapsados), separados por "|".
  Se registran con `ambiguous=false`.
- ambiguous_aliases: opcional, mismo formato, para alias compartidos por mas
  de una entidad (se registran con `ambiguous=true`; nunca asignan publicador
  automaticamente -- research.md #7).
- active: opcional, "true"/"false" (default true).

Si `id` ya existe en el fixture, la fila se trata como una AMPLIACION de esa
entidad: se agregan los alias nuevos (sin duplicar) y solo se sobreescriben
`canonical_name`/`entity_type`/`verification_source`/`active` con
--update-existing (por defecto, una fila con esos campos distintos a los ya
guardados se rechaza para evitar sobreescrituras accidentales).

El script SOLO escribe el archivo JSON del fixture; no toca la base de datos.
Para aplicar los cambios, recarga el fixture con
`python scripts/load_official_publishers.py` (o `POST /v2/admin/publishers/reload`).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.db.publishers import DEFAULT_FIXTURE_PATH, OfficialPublishersFixture
from app.db.publishers_admin import (
    REQUIRED_CSV_COLUMNS,
    AddPublishersError,
    merge_publishers,
)


def _read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise AddPublishersError(f"{csv_path}: archivo vacio o sin encabezado.")
        missing = REQUIRED_CSV_COLUMNS - set(reader.fieldnames)
        if missing:
            raise AddPublishersError(
                f"{csv_path}: faltan columnas obligatorias: {sorted(missing)}."
            )
        return list(reader)


def _run(csv_path: Path, fixture_path: Path, *, update_existing: bool, dry_run: bool) -> None:
    rows = _read_rows(csv_path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    summary = merge_publishers(data, rows, update_existing=update_existing)

    data["fixture_version"] = datetime.now(UTC).date().isoformat()
    data["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Reusa la validacion Pydantic de app.db.publishers para no escribir un
    # fixture que load_fixture() rechazaria despues.
    OfficialPublishersFixture.model_validate(data)

    for warning in summary.warnings:
        print(f"[aviso] {warning}")
    print(
        f"Publicadores nuevos: {summary.publishers_added} | "
        f"actualizados: {summary.publishers_updated} | "
        f"alias agregados: {summary.aliases_added} | "
        f"total en el fixture: {len(data['publishers'])}"
    )

    if dry_run:
        print("--dry-run: no se escribio el archivo.")
        return

    fixture_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Fixture actualizado: {fixture_path}")
    print(
        "Siguiente paso: python scripts/load_official_publishers.py "
        "(o POST /v2/admin/publishers/reload) para aplicar los cambios en la base local."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Amplia backend/data/official_publishers.json desde un CSV de entidades nuevas."
    )
    parser.add_argument(
        "--input", type=Path, required=True, help="Ruta al CSV de entidades nuevas."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Fixture a modificar (default: backend/data/official_publishers.json).",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Permite sobreescribir canonical_name/entity_type/verification_source/active "
        "de un id ya existente si la fila del CSV trae valores distintos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y muestra el resumen sin escribir el archivo.",
    )
    args = parser.parse_args()

    try:
        _run(
            args.input,
            args.fixture,
            update_existing=args.update_existing,
            dry_run=args.dry_run,
        )
    except AddPublishersError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
