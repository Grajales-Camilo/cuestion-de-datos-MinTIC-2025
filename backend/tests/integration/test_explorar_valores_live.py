"""Integracion T-302/T-303: `explorar_valores` (T4) contra Socrata real.

Hallazgo T-303 (2026-07-10): `explorar_valores` construia `LIKE ... ESCAPE
'\\'`, sintaxis SQL estandar que SoQL NO soporta (`400
query.compiler.malformed`); las pruebas con mocks (respx) nunca lo
detectaron porque no validan la gramatica real de Socrata. pruebas.md §2.3
exige "explorar_valores reales" precisamente para detectar esta clase de
drift/incompatibilidad; este archivo cierra ese hueco de cobertura.
"""

import os

import httpx
import pytest

from app.tools.explorar_valores import explorar_valores
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL

pytestmark = pytest.mark.integration

_DATASET_ID = "ji8i-4anb"


async def test_explorar_valores_finds_known_value_against_real_socrata() -> None:
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
        result = await explorar_valores(
            {"dataset_id": _DATASET_ID, "columna": "departamento", "termino_busqueda": "Antioquia"},
            http_client=http_client,
            app_token=app_token,
        )

    assert result["ok"] is True
    assert "Antioquia" in result["values"]


async def test_explorar_valores_no_match_returns_empty_not_error() -> None:
    """El termino de busqueda no debe tratarse como patron LIKE: buscar algo
    que no exista no debe fallar por sintaxis (regresion del bug ESCAPE)."""
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
        result = await explorar_valores(
            {
                "dataset_id": _DATASET_ID,
                "columna": "departamento",
                "termino_busqueda": "ZonaQueNoExiste123",
            },
            http_client=http_client,
            app_token=app_token,
        )

    assert result == {"ok": True, "values": [], "truncated": False}
