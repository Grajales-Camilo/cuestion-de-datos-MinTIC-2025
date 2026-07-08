"""Cliente HTTP puro para la Discovery API de Socrata (T-201, tasks.md).

Guia normativa de timeout/reintento: unica disponible es RNF-001 ("Consulta
Socrata <= 5s, timeout 10s, 1 reintento"), aplicada aqui por analogia a
Discovery API (no esta normada explicitamente para este endpoint). El 429
(throttling) se trata aparte: no consume el unico reintento de RNF-001
porque no es un fallo transitorio de red sino una señal explicita de limite
de tarifa.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

DISCOVERY_PATH = "/api/catalog/v1"

_REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_TRANSIENT_RETRY_DELAY_S = 1.0
_RATE_LIMIT_MAX_ATTEMPTS = 5
_RATE_LIMIT_DEFAULT_BACKOFF_S = 5.0


class DiscoveryApiError(Exception):
    """Fallo no recuperable al consultar la Discovery API (agotados los reintentos)."""


class DiscoveryClient:
    def __init__(self, http_client: httpx.AsyncClient, app_token: str | None = None) -> None:
        self._http_client = http_client
        self._app_token = app_token

    def _headers(self) -> dict[str, str]:
        if self._app_token:
            return {"X-App-Token": self._app_token}
        return {}

    async def _send(self, params: dict[str, str | int]) -> httpx.Response:
        response = await self._http_client.get(
            DISCOVERY_PATH,
            params=params,
            headers=self._headers(),
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response

    async def _get_page(self, domain: str, only: str, limit: int, offset: int) -> dict:
        params: dict[str, str | int] = {
            "domains": domain,
            "only": only,
            "limit": limit,
            "offset": offset,
        }
        rate_limit_attempts = 0
        retried_transient_once = False

        while True:
            try:
                response = await self._send(params)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    rate_limit_attempts += 1
                    if rate_limit_attempts > _RATE_LIMIT_MAX_ATTEMPTS:
                        raise DiscoveryApiError(
                            "Discovery API: limite de tarifa excedido tras "
                            f"{_RATE_LIMIT_MAX_ATTEMPTS} intentos"
                        ) from exc
                    await asyncio.sleep(_retry_after_seconds(exc.response))
                    continue
                if status >= 500 and not retried_transient_once:
                    retried_transient_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                raise DiscoveryApiError(f"Discovery API respondio {status}") from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if not retried_transient_once:
                    retried_transient_once = True
                    await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                    continue
                raise DiscoveryApiError("Discovery API no respondio tras 1 reintento") from exc
            else:
                return response.json()

    async def iter_pages(
        self, domain: str, page_size: int, only: str = "dataset"
    ) -> AsyncIterator[list[dict]]:
        """Pagina la Discovery API con limit/offset hasta agotar los resultados."""

        offset = 0
        while True:
            payload = await self._get_page(domain=domain, only=only, limit=page_size, offset=offset)
            results = payload.get("results", [])
            if not results:
                return
            yield results
            if len(results) < page_size:
                return
            offset += page_size


def _retry_after_seconds(response: httpx.Response) -> float:
    header_value = response.headers.get("Retry-After")
    if header_value is None:
        return _RATE_LIMIT_DEFAULT_BACKOFF_S
    try:
        return float(header_value)
    except ValueError:
        return _RATE_LIMIT_DEFAULT_BACKOFF_S
