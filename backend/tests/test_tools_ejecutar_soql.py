import httpx
import pytest
import respx

import app.tools.ejecutar_soql as ejecutar_soql_module
from app.tools import soda_client as soda_client_module
from app.tools.ejecutar_soql import ejecutar_soql
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL
from app.tools.soql_parser import ColumnInfo, DatasetCatalogInfo

DATASET_ID = "nudc-7mev"
PATH = f"/resource/{DATASET_ID}.json"

_ELIGIBLE_DATASET = DatasetCatalogInfo(
    dataset_id=DATASET_ID,
    api_active=True,
    eligibility_status="eligible",
    columns=(
        ColumnInfo("a_o", "low", "eligible"),
        ColumnInfo("desercion", "low", "eligible"),
        ColumnInfo("codigo_municipio", "low", "eligible"),
    ),
)


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
    async def fake_fetch(engine, dataset_id):
        if dataset_id != DATASET_ID:
            return None
        return _ELIGIBLE_DATASET

    monkeypatch.setattr(ejecutar_soql_module, "fetch_dataset_catalog_info", fake_fetch)


@respx.mock
async def test_ejecutar_soql_returns_rows_and_llm_view(http_client) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(200, json=[{"a_o": "2025", "prom": "3.2"}])
    )

    result = await ejecutar_soql(
        {
            "dataset_id": DATASET_ID,
            "soql": (
                "SELECT a_o, avg(desercion) AS prom WHERE codigo_municipio='05756' "
                "GROUP BY a_o ORDER BY a_o DESC"
            ),
            "purpose": "Serie anual de desercion para Sonson",
        },
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is True
    assert result["rows"] == [{"a_o": "2025", "prom": "3.2"}]
    assert result["row_count"] == 1
    assert result["llm_view"] == {
        "rows_shown": 1,
        "note": "al contexto del LLM entran max. 50 filas; el resto viaja directo a la Evidencia",
    }
    assert "source_url" in result and "executed_at" in result


async def test_ejecutar_soql_invalid_input_never_calls_socrata(http_client) -> None:
    result = await ejecutar_soql(
        {"dataset_id": "", "soql": "SELECT a_o", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


async def test_ejecutar_soql_unknown_dataset_is_dataset_inactive(http_client) -> None:
    result = await ejecutar_soql(
        {"dataset_id": "no-existe", "soql": "SELECT a_o", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result == {
        "ok": False,
        "error": {
            "code": "DATASET_INACTIVE",
            "message": "el dataset 'no-existe' no existe en el catalogo",
        },
    }


async def test_ejecutar_soql_select_star_rejected_by_guard_before_socrata(http_client) -> None:
    result = await ejecutar_soql(
        {"dataset_id": DATASET_ID, "soql": "SELECT *", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOQL_FORBIDDEN"


async def test_ejecutar_soql_unknown_column_reports_valid_columns(http_client) -> None:
    result = await ejecutar_soql(
        {"dataset_id": DATASET_ID, "soql": "SELECT no_existe", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOQL_UNKNOWN_COLUMN"
    assert result["error"]["valid_columns"] == ["a_o", "codigo_municipio", "desercion"]


@respx.mock
async def test_ejecutar_soql_maps_socrata_400_to_soql_syntax(http_client) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(400, json={"message": "no such column 'a_o' in table"})
    )

    result = await ejecutar_soql(
        {"dataset_id": DATASET_ID, "soql": "SELECT a_o", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOQL_SYNTAX"
    assert "a_o" in result["error"]["message"]


@respx.mock
async def test_ejecutar_soql_maps_timeout_after_one_retry(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(side_effect=responder)

    result = await ejecutar_soql(
        {"dataset_id": DATASET_ID, "soql": "SELECT a_o", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOCRATA_TIMEOUT"


async def test_ejecutar_soql_dataset_not_eligible(http_client, monkeypatch) -> None:
    async def fake_fetch(engine, dataset_id):
        return DatasetCatalogInfo(
            dataset_id=dataset_id,
            api_active=True,
            eligibility_status="blocked",
            columns=(),
        )

    monkeypatch.setattr(ejecutar_soql_module, "fetch_dataset_catalog_info", fake_fetch)

    result = await ejecutar_soql(
        {"dataset_id": DATASET_ID, "soql": "SELECT a_o", "purpose": "x"},
        engine=None,
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "EVIDENCE_NOT_ELIGIBLE"
