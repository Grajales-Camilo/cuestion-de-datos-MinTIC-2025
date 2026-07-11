r"""T4 `explorar_valores` (contracts/agent-tools.md §T4, RNF-011).

`termino_busqueda` se sanitiza antes de interpolar en el `$where` de SODA:
escapa `'` (literal SQL) y escapa `%`/`_` (comodines de `LIKE`) con `\`,
para que el termino se compare de forma literal y no como patron.

Correccion verificada contra Socrata real (hallazgo T-303, 2026-07-10): la
gramatica SoQL NO soporta la clausula `LIKE ... ESCAPE '\'` (SQL estandar);
Socrata la rechaza con `400 query.compiler.malformed`, indistinguible en
ejecucion real de un timeout si ademas el cliente HTTP no tiene `base_url`
configurado (ver runner.py). Esto hacia que T4 nunca funcionara contra el
servicio real, aunque las pruebas con mocks no lo detectaban. Se confirmo
empiricamente contra `ji8i-4anb` que Socrata SI trata `\` como caracter de
escape POR DEFECTO sin declarar `ESCAPE`: `LIKE upper('_ntioquia')` (sin
escapar) matchea "Antioquia" (comodin activo); `LIKE upper('\_ntioquia')`
(escapado, SIN clausula ESCAPE) no matchea nada (tratado como literal), y
lo mismo para `%`. La sanitizacion con backslash de `sanitize_like_term`
ya era correcta; solo sobraba la clausula `ESCAPE '\'` al final del WHERE.

Hallazgo T-402 (2026-07-11, ejecucion real con LLM real): el contrato (§T4)
ya decia "columna de texto", pero esta funcion no lo validaba -- envolvia
CUALQUIER columna en `upper(...) LIKE ...`, incluida una NUMERICA (p. ej.
una columna de año). Socrata rechaza eso con `query.soql.type-mismatch`, un
error que el LLM no sabe autocorregir (no es un problema de sintaxis de la
consulta, es un uso incorrecto de la herramienta) y que en ejecucion real
hizo que el agente repitiera la misma llamada rota hasta agotar el
presupuesto de pasos. Se agrega una validacion previa contra
`catalog_columns.data_type` que rechaza de forma determinista, sin llamar a
Socrata, con un mensaje que le dice al LLM que use `ejecutar_soql`
directamente. Comparacion insensible a mayusculas porque los valores reales
observados en `catalog_columns.data_type` (via Discovery API) no siguen una
convencion unica: se vio "Number"/"Text" en datasets reales durante esta
misma investigacion, mientras que `perfilar_dataset._CUTOFF_CANDIDATE_DATA_TYPES`
asume nombres internos en minuscula ("calendar_date"); no se unifica esa
inconsistencia preexistente aqui, fuera de alcance de este hallazgo.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tools.catalog_lookup import fetch_columns_catalog
from app.tools.errors import error_envelope, validation_error_envelope
from app.tools.soda_client import SocrataQueryError, SodaClient

VALUES_LIMIT = 20

_NON_TEXT_DATA_TYPE_MARKERS = (
    "number",
    "int",
    "float",
    "double",
    "decimal",
    "money",
    "date",
    "timestamp",
    "calendar",
    "checkbox",
    "boolean",
)


class ExplorarValoresInput(BaseModel):
    dataset_id: str = Field(min_length=1)
    columna: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    termino_busqueda: str = Field(min_length=1, max_length=200)


def sanitize_like_term(termino: str) -> str:
    """Escapa `\\`, `%`, `_` y `'` para uso literal dentro de `LIKE` (Socrata
    trata `\\` como caracter de escape por defecto, sin clausula `ESCAPE`)."""

    escaped = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped.replace("'", "''")


def _is_text_like(data_type: str) -> bool:
    lowered = data_type.lower()
    return not any(marker in lowered for marker in _NON_TEXT_DATA_TYPE_MARKERS)


async def explorar_valores(
    raw_input: dict,
    *,
    engine: AsyncEngine,
    http_client: httpx.AsyncClient,
    app_token: str | None = None,
) -> dict:
    try:
        parsed_input = ExplorarValoresInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    column = parsed_input.columna
    columns = await fetch_columns_catalog(engine, parsed_input.dataset_id)
    column_info = next((c for c in columns if c.field_name == column), None)
    if column_info is None:
        return error_envelope(
            "SOQL_UNKNOWN_COLUMN",
            f"la columna {column!r} no existe en el dataset {parsed_input.dataset_id!r}",
        )
    if not _is_text_like(column_info.data_type):
        return error_envelope(
            "EXPLORAR_VALORES_NOT_TEXT",
            f"la columna {column!r} es de tipo {column_info.data_type!r}, no de texto; "
            "explorar_valores solo sirve para columnas de texto (compara con LIKE). "
            "Filtra esta columna directamente en ejecutar_soql con '=' o un rango, sin "
            "upper()/LIKE.",
        )

    safe_term = sanitize_like_term(parsed_input.termino_busqueda)
    where = f"upper({column}) LIKE upper('%{safe_term}%')"

    client = SodaClient(http_client, app_token=app_token)
    try:
        result = await client.query(
            parsed_input.dataset_id,
            select=column,
            where=where,
            group=column,
            limit=VALUES_LIMIT + 1,
        )
    except SocrataQueryError as exc:
        return error_envelope(exc.code, exc.message)

    rows = result.rows
    truncated = len(rows) > VALUES_LIMIT
    values = [row[column] for row in rows[:VALUES_LIMIT] if column in row]
    return {"ok": True, "values": values, "truncated": truncated}
