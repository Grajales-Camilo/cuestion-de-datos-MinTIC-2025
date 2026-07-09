"""Integracion T-202: una pagina real del dataset DIVIPOLA produce filas validas.

Deliberadamente pequeña (page_size=5) para no depender de volumen ni tardar;
sirve tambien para detectar drift si el dataset `gdxc-w37w` cambia de forma
(pruebas.md, mismo espiritu que test_ingest_catalog_live_discovery.py).
"""

import os

import httpx
import pytest

from app.catalog.divipola_client import DivipolaClient
from app.db.divipola import municipality_entry_from_row

pytestmark = pytest.mark.integration

_SODA_BASE_URL = "https://www.datos.gov.co"
_DATASET_ID = "gdxc-w37w"


async def test_one_real_page_produces_valid_rows() -> None:
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    async with httpx.AsyncClient(base_url=_SODA_BASE_URL) as http_client:
        client = DivipolaClient(http_client, dataset_id=_DATASET_ID, app_token=app_token)
        pages = []
        async for page in client.iter_rows(page_size=5):
            pages.append(page)
            break

    assert pages
    rows = pages[0]
    assert len(rows) == 5

    entries = [municipality_entry_from_row(row) for row in rows]
    for entry in entries:
        assert len(entry.code) == 5
        assert entry.department_code
        assert entry.name
