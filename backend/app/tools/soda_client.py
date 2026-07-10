"""Cliente SODA generico para consultas de columnas/filas (T2, T4, T5).

Mismo patron de timeout/reintento que `app/catalog/discovery_client.py` y
`app/catalog/divipola_client.py` (RNF-001: timeout 10s, 1 reintento ante 5xx
o timeout transitorio), pero recibe los parametros SoQL discretos
(`$select`/`$where`/`$group`/`$having`/`$order`/`$limit`/`$offset`) que
produce `app/tools/soql_parser.py` en vez de paginar con `$limit`/`$offset`
fijos.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

SOCRATA_RESOURCE_BASE_URL = "https://www.datos.gov.co"

_REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_TRANSIENT_RETRY_DELAY_S = 1.0


class SocrataQueryError(Exception):
    """Fallo al ejecutar una consulta SODA; `code` sigue agent-tools.md §T5."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SodaQueryResult:
    rows: list[dict]
    executed_at: datetime
    source_url: str


def _extract_socrata_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    return str(payload)[:500]


class SodaClient:
    def __init__(self, http_client: httpx.AsyncClient, app_token: str | None = None) -> None:
        self._http_client = http_client
        self._app_token = app_token

    def _headers(self) -> dict[str, str]:
        return {"X-App-Token": self._app_token} if self._app_token else {}

    async def query(
        self,
        dataset_id: str,
        *,
        select: str | None = None,
        where: str | None = None,
        group: str | None = None,
        having: str | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SodaQueryResult:
        params: dict[str, str | int] = {}
        if select is not None:
            params["$select"] = select
        if where is not None:
            params["$where"] = where
        if group is not None:
            params["$group"] = group
        if having is not None:
            params["$having"] = having
        if order is not None:
            params["$order"] = order
        if limit is not None:
            params["$limit"] = limit
        if offset is not None:
            params["$offset"] = offset

        path = f"/resource/{dataset_id}.json"
        retried_once = False

        while True:
            try:
                response = await self._http_client.get(
                    path, params=params, headers=self._headers(), timeout=_REQUEST_TIMEOUT
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 400:
                    raise SocrataQueryError(
                        "SOQL_SYNTAX", _extract_socrata_message(exc.response)
                    ) from exc
                if status == 404:
                    raise SocrataQueryError(
                        "DATASET_INACTIVE", f"Socrata no encontro el dataset {dataset_id!r}"
                    ) from exc
                if status >= 500 and not retried_once:
                    retried_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                detail = _extract_socrata_message(exc.response)
                message = f"Socrata respondio {status}: {detail}"
                raise SocrataQueryError("SOCRATA_ERROR", message) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if not retried_once:
                    retried_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                raise SocrataQueryError(
                    "SOCRATA_TIMEOUT", "Socrata no respondio tras 1 reintento"
                ) from exc
            else:
                return SodaQueryResult(
                    rows=response.json(),
                    executed_at=datetime.now(UTC),
                    source_url=str(response.request.url),
                )
