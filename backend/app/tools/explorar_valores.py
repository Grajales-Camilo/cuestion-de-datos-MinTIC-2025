r"""T4 `explorar_valores` (contracts/agent-tools.md §T4, RNF-011).

`termino_busqueda` se sanitiza antes de interpolar en el `$where` de SODA:
escapa `'` (literal SQL), y escapa `%`/`_` (comodines de `LIKE`) con `\`
seguido de `ESCAPE '\'` explicito, para que el termino se compare de forma
literal y no como patron.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.tools.errors import error_envelope, validation_error_envelope
from app.tools.soda_client import SocrataQueryError, SodaClient

VALUES_LIMIT = 20


class ExplorarValoresInput(BaseModel):
    dataset_id: str = Field(min_length=1)
    columna: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    termino_busqueda: str = Field(min_length=1, max_length=200)


def sanitize_like_term(termino: str) -> str:
    """Escapa `\\`, `%`, `_` y `'` para uso literal dentro de `LIKE ... ESCAPE '\\'`."""

    escaped = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped.replace("'", "''")


async def explorar_valores(
    raw_input: dict, *, http_client: httpx.AsyncClient, app_token: str | None = None
) -> dict:
    try:
        parsed_input = ExplorarValoresInput.model_validate(raw_input)
    except ValidationError as exc:
        return validation_error_envelope(exc)

    column = parsed_input.columna
    safe_term = sanitize_like_term(parsed_input.termino_busqueda)
    where = f"upper({column}) LIKE upper('%{safe_term}%') ESCAPE '\\'"

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
