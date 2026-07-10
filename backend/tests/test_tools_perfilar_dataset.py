import httpx
import pytest
import respx

import app.tools.perfilar_dataset as perfilar_dataset_module
from app.tools import soda_client as soda_client_module
from app.tools.catalog_lookup import ColumnCatalogRow
from app.tools.perfilar_dataset import perfilar_dataset
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL

DATASET_ID = "2d3i-f9wd"
PATH = f"/resource/{DATASET_ID}.json"

_COLUMNS = [
    ColumnCatalogRow("estado_intervencion", "text", "low", "eligible"),
    ColumnCatalogRow("fecha_inicial", "calendar_date", "low", "eligible"),
    ColumnCatalogRow("fecha_final", "calendar_date", "low", "eligible"),
    ColumnCatalogRow("beneficiario_id", "text", "high", "blocked"),
]


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as client:
        yield client


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(soda_client_module.asyncio, "sleep", fake_sleep)


@pytest.fixture(autouse=True)
def fake_catalog_lookup(monkeypatch):
    async def fake_fetch_columns_catalog(engine, dataset_id):
        return _COLUMNS

    captured: dict = {}

    async def fake_update_profile_cache(engine, dataset_id, column_updates, cutoff_at_iso):
        captured["dataset_id"] = dataset_id
        captured["column_updates"] = column_updates
        captured["cutoff_at_iso"] = cutoff_at_iso

    monkeypatch.setattr(
        perfilar_dataset_module, "fetch_columns_catalog", fake_fetch_columns_catalog
    )
    monkeypatch.setattr(
        perfilar_dataset_module, "update_profile_cache", fake_update_profile_cache
    )
    return captured


def _responder(request: httpx.Request) -> httpx.Response:
    select = request.url.params.get("$select", "")
    if select == "count(*) AS total":
        return httpx.Response(200, json=[{"total": "15230"}])
    if select.startswith("max(fecha_final)"):
        return httpx.Response(200, json=[{"max_value": "2025-12-31T00:00:00.000"}])
    if select.startswith("count(*) AS total, count("):
        return httpx.Response(200, json=[{"total": "15230", "non_null": "15000"}])
    if request.url.params.get("$group"):
        return httpx.Response(
            200, json=[{"estado_intervencion": "Finalizado"}, {"estado_intervencion": "Ejecucion"}]
        )
    return httpx.Response(200, json=[])


@respx.mock
async def test_perfilar_dataset_returns_profile_and_cutoff_hint(
    http_client, fake_catalog_lookup
) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(side_effect=_responder)

    result = await perfilar_dataset(
        {
            "dataset_id": DATASET_ID,
            "columns_of_interest": ["estado_intervencion", "fecha_inicial"],
        },
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is True
    assert result["total_rows_estimate"] == 15230
    assert result["latest_observed_cutoff_hint"] == {
        "latest_observed_cutoff_at": "2025-12-31T00:00:00.000",
        "method": "max_temporal_column",
        "column": "fecha_final",
        "confidence": 0.85,
        "inferred_at": result["latest_observed_cutoff_hint"]["inferred_at"],
    }
    profile_by_field = {item["field_name"]: item for item in result["profile"]}
    assert profile_by_field["estado_intervencion"]["distinct_sample"] == [
        "Finalizado",
        "Ejecucion",
    ]
    assert profile_by_field["estado_intervencion"]["null_ratio"] == pytest.approx(0.0151, abs=1e-4)
    # fecha_inicial is not the chosen cutoff candidate (fecha_final wins by keyword match)
    assert profile_by_field["fecha_inicial"]["distinct_sample"] == []

    # cache write captured with the resolved profile
    assert fake_catalog_lookup["dataset_id"] == DATASET_ID
    assert fake_catalog_lookup["cutoff_at_iso"] == "2025-12-31T00:00:00.000"


@respx.mock
async def test_perfilar_dataset_does_not_fetch_sample_values_for_high_pii_column(
    http_client, fake_catalog_lookup
) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(side_effect=_responder)

    result = await perfilar_dataset(
        {"dataset_id": DATASET_ID, "columns_of_interest": ["beneficiario_id"]},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is True
    assert result["profile"][0]["distinct_sample"] == []
    update = fake_catalog_lookup["column_updates"][0]
    assert update.sample_values is None


async def test_perfilar_dataset_rejects_too_many_columns(http_client) -> None:
    result = await perfilar_dataset(
        {"dataset_id": DATASET_ID, "columns_of_interest": ["a", "b", "c", "d", "e", "f"]},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


async def test_perfilar_dataset_unknown_column_reports_valid_ones(http_client) -> None:
    result = await perfilar_dataset(
        {"dataset_id": DATASET_ID, "columns_of_interest": ["no_existe"]},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOQL_UNKNOWN_COLUMN"
    assert "beneficiario_id" in result["error"]["valid_columns"]


@respx.mock
async def test_perfilar_dataset_maps_socrata_timeout(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(side_effect=responder)

    result = await perfilar_dataset(
        {"dataset_id": DATASET_ID, "columns_of_interest": []},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOCRATA_TIMEOUT"
