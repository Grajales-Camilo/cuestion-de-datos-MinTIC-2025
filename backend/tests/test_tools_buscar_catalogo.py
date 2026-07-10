from datetime import UTC, datetime

import pytest

import app.tools.buscar_catalogo as buscar_catalogo_module
from app.catalog.search import CatalogSearchItem, CatalogSearchSummary
from app.tools.buscar_catalogo import DESCRIPTION_SNIPPET_MAX_CHARS, buscar_catalogo

DATASET_ID = "2d3i-f9wd"


def _search_item(**overrides: object) -> CatalogSearchItem:
    defaults: dict[str, object] = {
        "dataset_id": DATASET_ID,
        "name": "Cooperacion Internacional No Reembolsable",
        "publisher": "APC Colombia",
        "official_publisher_id": "apc-colombia",
        "publisher_verification_status": "verified",
        "pii_risk_level": "low",
        "eligibility_status": "eligible",
        "eligibility_reasons": [],
        "similarity": 0.84,
        "row_count": 15230,
        "data_updated_at": datetime(2026, 1, 10, tzinfo=UTC),
        "latest_observed_cutoff_at": None,
        "metadata_synced_at": datetime(2026, 7, 5, tzinfo=UTC),
        "index_stale": False,
        "columns_preview": ["monto_aporte_en_usd"],
    }
    defaults.update(overrides)
    return CatalogSearchItem(**defaults)


@pytest.fixture(autouse=True)
def fake_search_and_columns(monkeypatch):
    async def fake_search_catalog(engine, *, embedding_client, query, k):
        return CatalogSearchSummary(query=query, results=[_search_item()])

    async def fake_fetch_descriptions_and_columns(engine, dataset_ids):
        return {
            DATASET_ID: {
                "description": "x" * (DESCRIPTION_SNIPPET_MAX_CHARS + 50),
                "columns": [
                    {
                        "field_name": "monto_aporte_en_usd",
                        "data_type": "number",
                        "description": "Monto en USD",
                    }
                ],
            }
        }

    monkeypatch.setattr(buscar_catalogo_module, "search_catalog", fake_search_catalog)
    monkeypatch.setattr(
        buscar_catalogo_module,
        "_fetch_descriptions_and_columns",
        fake_fetch_descriptions_and_columns,
    )


async def test_buscar_catalogo_returns_full_columns_and_truncated_description() -> None:
    result = await buscar_catalogo(
        {"query": "recursos de cooperacion internacional por municipio", "k": 8},
        engine=None,
        embedding_client=None,
    )

    assert result["ok"] is True
    item = result["results"][0]
    assert item["dataset_id"] == DATASET_ID
    assert len(item["description_snippet"]) == DESCRIPTION_SNIPPET_MAX_CHARS
    assert item["columns"] == [
        {"field_name": "monto_aporte_en_usd", "data_type": "number", "description": "Monto en USD"}
    ]
    assert item["eligibility_status"] == "eligible"


async def test_buscar_catalogo_rejects_short_query() -> None:
    result = await buscar_catalogo({"query": "ab", "k": 8}, engine=None, embedding_client=None)

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


async def test_buscar_catalogo_rejects_k_above_10() -> None:
    result = await buscar_catalogo(
        {"query": "consulta valida", "k": 11}, engine=None, embedding_client=None
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


async def test_buscar_catalogo_defaults_k_to_8() -> None:
    result = await buscar_catalogo(
        {"query": "consulta valida por defecto"}, engine=None, embedding_client=None
    )

    assert result["ok"] is True
