"""Cliente HTTP puro para el recurso SODA del dataset DIVIPOLA (T-202).

Guia normativa de timeout/reintento: RNF-001 ("Consulta Socrata <= 5s,
timeout 10s, 1 reintento"). Paginacion con `$limit`/`$offset` ordenada por
`:id` (identificador de fila SODA) para evitar filas duplicadas/perdidas
entre paginas, siguiendo la recomendacion de la documentacion de Socrata
para paginacion estable.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

_REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_TRANSIENT_RETRY_DELAY_S = 1.0


class SocrataResourceError(Exception):
    """Fallo no recuperable al consultar el recurso SODA (agotado el reintento)."""


class DivipolaClient:
    def __init__(
        self, http_client: httpx.AsyncClient, dataset_id: str, app_token: str | None = None
    ) -> None:
        self._http_client = http_client
        self._dataset_id = dataset_id
        self._app_token = app_token

    def _headers(self) -> dict[str, str]:
        if self._app_token:
            return {"X-App-Token": self._app_token}
        return {}

    async def _get_page(self, limit: int, offset: int) -> list[dict]:
        params: dict[str, str | int] = {"$limit": limit, "$offset": offset, "$order": ":id"}
        retried_once = False

        while True:
            try:
                response = await self._http_client.get(
                    f"/resource/{self._dataset_id}.json",
                    params=params,
                    headers=self._headers(),
                    timeout=_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status >= 500 and not retried_once:
                    retried_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                raise SocrataResourceError(f"DIVIPOLA: la API respondio {status}") from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if not retried_once:
                    retried_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                raise SocrataResourceError(
                    "DIVIPOLA: la API no respondio tras 1 reintento"
                ) from exc
            else:
                return response.json()

    async def iter_rows(self, page_size: int = 1000) -> AsyncIterator[list[dict]]:
        """Pagina el recurso SODA hasta agotar los resultados."""

        offset = 0
        while True:
            rows = await self._get_page(limit=page_size, offset=offset)
            if not rows:
                return
            yield rows
            if len(rows) < page_size:
                return
            offset += page_size
