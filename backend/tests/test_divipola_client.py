import httpx
import pytest
import respx

from app.catalog import divipola_client as divipola_client_module
from app.catalog.divipola_client import DivipolaClient, SocrataResourceError

BASE_URL = "https://www.datos.gov.co"
DATASET_ID = "gdxc-w37w"
PATH = f"/resource/{DATASET_ID}.json"


def _rows(codes: list[str]) -> list[dict]:
    return [{"cod_mpio": code} for code in codes]


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        yield client


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(divipola_client_module.asyncio, "sleep", fake_sleep)
    return recorded


@respx.mock
async def test_iter_rows_stops_on_partial_page(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("$offset", "0"))
        if offset == 0:
            return httpx.Response(200, json=_rows(["05001", "05002"]))
        return httpx.Response(200, json=_rows(["05004"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    pages = [page async for page in client.iter_rows(page_size=2)]

    assert len(pages) == 2
    assert [row["cod_mpio"] for row in pages[0]] == ["05001", "05002"]
    assert [row["cod_mpio"] for row in pages[1]] == ["05004"]


@respx.mock
async def test_iter_rows_stops_on_empty_page(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("$offset", "0"))
        if offset == 0:
            return httpx.Response(200, json=_rows(["05001", "05002"]))
        return httpx.Response(200, json=[])

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    pages = [page async for page in client.iter_rows(page_size=2)]

    assert len(pages) == 1


@respx.mock
async def test_single_retry_on_timeout_then_success(http_client) -> None:
    attempts = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(200, json=_rows(["05001"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    pages = [page async for page in client.iter_rows(page_size=10)]

    assert attempts["count"] == 2
    assert len(pages) == 1


@respx.mock
async def test_second_timeout_raises_socrata_resource_error(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    with pytest.raises(SocrataResourceError):
        async for _ in client.iter_rows(page_size=10):
            pass


@respx.mock
async def test_single_retry_on_5xx_then_success(http_client) -> None:
    attempts = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json=_rows(["05001"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    pages = [page async for page in client.iter_rows(page_size=10)]

    assert attempts["count"] == 2
    assert len(pages) == 1


@respx.mock
async def test_non_transient_error_raises_immediately(http_client) -> None:
    respx.get(f"{BASE_URL}{PATH}").mock(return_value=httpx.Response(404, json={"error": "nope"}))

    client = DivipolaClient(http_client, dataset_id=DATASET_ID)
    with pytest.raises(SocrataResourceError):
        async for _ in client.iter_rows(page_size=10):
            pass


@respx.mock
async def test_app_token_header_sent_only_when_configured(http_client) -> None:
    captured_headers: list[httpx.Headers] = []

    def responder(request: httpx.Request) -> httpx.Response:
        captured_headers.append(request.headers)
        return httpx.Response(200, json=[])

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client_without_token = DivipolaClient(http_client, dataset_id=DATASET_ID, app_token=None)
    async for _ in client_without_token.iter_rows(page_size=10):
        pass
    assert "X-App-Token" not in captured_headers[0]

    captured_headers.clear()
    client_with_token = DivipolaClient(
        http_client, dataset_id=DATASET_ID, app_token="secret-token-value"
    )
    async for _ in client_with_token.iter_rows(page_size=10):
        pass
    assert captured_headers[0]["X-App-Token"] == "secret-token-value"
