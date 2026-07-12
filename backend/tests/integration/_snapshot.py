"""Respaldo/restauración de tablas para pruebas de integración que corren
contra la base local compartida.

Esa base puede tener datos reales cargados (catálogo de datos.gov.co,
DIVIPOLA, tipologías DNP, publicadores oficiales) que otro trabajo del
proyecto necesita conservar. Las pruebas que necesitan una tabla vacía para
sembrar datos sintéticos deben respaldarla antes y restaurarla después con
las funciones de este módulo, en vez de borrar sin más.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_BACKUP_PREFIX = "_test_backup_"


async def backup_tables(connection: AsyncConnection, *table_names: str) -> None:
    """Copia el contenido actual de cada tabla a una tabla de respaldo real
    (no TEMP: debe sobrevivir a que el pool async use otra conexión física
    entre el respaldo y la restauración)."""
    for name in table_names:
        backup = f"{_BACKUP_PREFIX}{name}"
        await connection.execute(text(f"DROP TABLE IF EXISTS {backup}"))
        await connection.execute(text(f"CREATE TABLE {backup} AS TABLE {name}"))


async def restore_tables(connection: AsyncConnection, *table_names: str) -> None:
    """Vacía y restaura cada tabla desde su respaldo.

    `table_names` debe ir en orden padre-a-hijo (ej. catalog_datasets,
    catalog_columns, catalog_embeddings): se borra en orden inverso (hijos
    primero) y se inserta en el orden dado (padres primero), respetando las
    FK en ambos sentidos.
    """
    for name in reversed(table_names):
        await connection.execute(text(f"DELETE FROM {name}"))
    for name in table_names:
        backup = f"{_BACKUP_PREFIX}{name}"
        await connection.execute(text(f"INSERT INTO {name} SELECT * FROM {backup}"))
        await connection.execute(text(f"DROP TABLE {backup}"))
