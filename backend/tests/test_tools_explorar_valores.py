import httpx
import pytest
import respx

from app.tools import soda_client as soda_client_module
from app.tools.explorar_valores import explorar_valores, sanitize_like_term
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL

DATASET_ID = "thui-g47e"
PATH = f"/resource/{DATASET_ID}.json"


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as client:
        yield client


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(soda_client_module.asyncio, "sleep", fake_sleep)


def test_sanitize_like_term_escapes_quote_percent_and_underscore() -> None:
    assert sanitize_like_term("100%_ok's") == "100\\%\\_ok''s"


def test_sanitize_like_term_escapes_backslash_before_wildcards() -> None:
    assert sanitize_like_term("a\\b") == "a\\\\b"


@respx.mock
async def test_explorar_valores_where_clause_has_no_escape_keyword(http_client) -> None:
    """Regresion T-303 (2026-07-10): SoQL no soporta `LIKE ... ESCAPE '\\'`
    (SQL estandar); Socrata la rechaza con 400 `query.compiler.malformed`.
    Verificado empiricamente que Socrata escapa `\\` por defecto sin esa
    clausula, asi que el `$where` real nunca debe incluir la palabra
    `ESCAPE`."""
    route = respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(200, json=[])
    )

    await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "departamento", "termino_busqueda": "Antioquia"},
        http_client=http_client,
    )

    sent_where = route.calls.last.request.url.params["$where"]
    assert "ESCAPE" not in sent_where.upper()


@respx.mock
async def test_explorar_valores_returns_matching_distinct_values(http_client) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(
            200, json=[{"nomindicador": "Proporcion de partos por cesarea"}]
        )
    )

    result = await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "nomindicador", "termino_busqueda": "cesárea"},
        http_client=http_client,
    )

    assert result == {
        "ok": True,
        "values": ["Proporcion de partos por cesarea"],
        "truncated": False,
    }


@respx.mock
async def test_explorar_valores_marks_truncated_when_over_limit(http_client) -> None:
    rows = [{"col": f"valor{i}"} for i in range(21)]
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(200, json=rows)
    )

    result = await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "col", "termino_busqueda": "valor"},
        http_client=http_client,
    )

    assert result["ok"] is True
    assert len(result["values"]) == 20
    assert result["truncated"] is True


async def test_explorar_valores_invalid_column_name_is_invalid_input(http_client) -> None:
    result = await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "1invalido", "termino_busqueda": "x"},
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


@respx.mock
async def test_explorar_valores_maps_socrata_timeout(http_client) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(side_effect=responder)

    result = await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "col", "termino_busqueda": "x"},
        http_client=http_client,
    )

    assert result == {
        "ok": False,
        "error": {"code": "SOCRATA_TIMEOUT", "message": "Socrata no respondio tras 1 reintento"},
    }


@respx.mock
async def test_explorar_valores_never_raises_on_socrata_400(http_client) -> None:
    respx.get(f"{SOCRATA_RESOURCE_BASE_URL}{PATH}").mock(
        return_value=httpx.Response(400, json={"message": "columna invalida"})
    )

    result = await explorar_valores(
        {"dataset_id": DATASET_ID, "columna": "col", "termino_busqueda": "x"},
        http_client=http_client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "SOQL_SYNTAX"
