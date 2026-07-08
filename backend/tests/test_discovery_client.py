import httpx
import pytest
import respx

from app.catalog import discovery_client as discovery_client_module
from app.catalog.discovery_client import DiscoveryApiError, DiscoveryClient

BASE_URL = "https://api.us.socrata.com"
PATH = "/api/catalog/v1"


def _page_response(ids: list[str]) -> dict:
    return {"results": [{"resource": {"id": i}} for i in ids], "resultSetSize": len(ids)}


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        yield client


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(discovery_client_module.asyncio, "sleep", fake_sleep)
    return recorded


@respx.mock
async def test_iter_pages_stops_on_partial_page(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        if offset == 0:
            return httpx.Response(200, json=_page_response(["a", "b"]))
        return httpx.Response(200, json=_page_response(["c"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    pages = [page async for page in client.iter_pages("www.datos.gov.co", page_size=2)]

    assert len(pages) == 2
    assert [item["resource"]["id"] for item in pages[0]] == ["a", "b"]
    assert [item["resource"]["id"] for item in pages[1]] == ["c"]


@respx.mock
async def test_iter_pages_stops_on_empty_page(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        if offset == 0:
            return httpx.Response(200, json=_page_response(["a", "b"]))
        return httpx.Response(200, json=_page_response([]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    pages = [page async for page in client.iter_pages("www.datos.gov.co", page_size=2)]

    assert len(pages) == 1


@respx.mock
async def test_single_retry_on_timeout_then_success(http_client) -> None:
    attempts = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(200, json=_page_response(["a"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    pages = [page async for page in client.iter_pages("www.datos.gov.co", page_size=10)]

    assert attempts["count"] == 2
    assert len(pages) == 1


@respx.mock
async def test_second_timeout_raises_discovery_api_error(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    with pytest.raises(DiscoveryApiError):
        async for _ in client.iter_pages("www.datos.gov.co", page_size=10):
            pass


@respx.mock
async def test_single_retry_on_5xx_then_success(http_client) -> None:
    attempts = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json=_page_response(["a"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    pages = [page async for page in client.iter_pages("www.datos.gov.co", page_size=10)]

    assert attempts["count"] == 2
    assert len(pages) == 1


@respx.mock
async def test_429_respects_retry_after_header(http_client, no_real_sleep) -> None:
    attempts = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": "throttled"})
        return httpx.Response(200, json=_page_response(["a"]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client = DiscoveryClient(http_client)
    pages = [page async for page in client.iter_pages("www.datos.gov.co", page_size=10)]

    assert attempts["count"] == 2
    assert len(pages) == 1
    assert 7.0 in no_real_sleep


@respx.mock
async def test_429_gives_up_after_max_attempts(http_client) -> None:
    respx.get(f"{BASE_URL}{PATH}").mock(
        return_value=httpx.Response(429, json={"error": "throttled"})
    )

    client = DiscoveryClient(http_client)
    with pytest.raises(DiscoveryApiError):
        async for _ in client.iter_pages("www.datos.gov.co", page_size=10):
            pass


@respx.mock
async def test_app_token_header_sent_only_when_configured(http_client) -> None:
    captured_headers: list[httpx.Headers] = []

    def responder(request: httpx.Request) -> httpx.Response:
        captured_headers.append(request.headers)
        return httpx.Response(200, json=_page_response([]))

    respx.get(f"{BASE_URL}{PATH}").mock(side_effect=responder)

    client_without_token = DiscoveryClient(http_client, app_token=None)
    async for _ in client_without_token.iter_pages("www.datos.gov.co", page_size=10):
        pass
    assert "X-App-Token" not in captured_headers[0]

    captured_headers.clear()
    client_with_token = DiscoveryClient(http_client, app_token="secret-token-value")
    async for _ in client_with_token.iter_pages("www.datos.gov.co", page_size=10):
        pass
    assert captured_headers[0]["X-App-Token"] == "secret-token-value"


@respx.mock
async def test_discovery_api_error_never_includes_token_value(http_client) -> None:
    respx.get(f"{BASE_URL}{PATH}").mock(return_value=httpx.Response(500))

    client = DiscoveryClient(http_client, app_token="super-secret-token")
    with pytest.raises(DiscoveryApiError) as exc_info:
        async for _ in client.iter_pages("www.datos.gov.co", page_size=10):
            pass

    assert "super-secret-token" not in str(exc_info.value)
