from datetime import UTC, datetime

from pydantic import SecretStr

from app.catalog.search import CatalogSearchItem, CatalogSearchSummary


class DummySettings:
    sqlalchemy_database_url = "postgresql+psycopg://usuario:clave@localhost:5432/no_db"
    google_api_key = SecretStr("fake-google-key")
    embedding_model = "gemini-embedding-2"
    catalog_stale_after_days = 8


async def test_catalog_search_trims_query_and_returns_contract(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    async def fake_search(**kwargs):
        assert kwargs["query"] == "desercion escolar"
        assert kwargs["k"] == 5
        return CatalogSearchSummary(
            query=kwargs["query"],
            results=[
                CatalogSearchItem(
                    dataset_id="nudc-7mev",
                    name="MEN Estadisticas en Educacion",
                    publisher="Ministerio de Educacion Nacional",
                    official_publisher_id="men",
                    publisher_verification_status="verified",
                    pii_risk_level="low",
                    eligibility_status="eligible",
                    eligibility_reasons=[],
                    similarity=0.87,
                    row_count=250000,
                    data_updated_at=datetime(2026, 3, 15, tzinfo=UTC),
                    latest_observed_cutoff_at=None,
                    metadata_synced_at=datetime(2026, 7, 5, tzinfo=UTC),
                    index_stale=False,
                    columns_preview=["a_o", "codigo_municipio"],
                )
            ],
        )

    monkeypatch.setattr(main, "catalog_search_with_platform_loop", fake_search)
    main.app.state.settings = DummySettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(
            "/v2/catalog/search",
            params={"q": "  desercion escolar  ", "k": 5},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "desercion escolar"
    assert body["results"][0]["dataset_id"] == "nudc-7mev"
    assert body["results"][0]["latest_observed_cutoff_at"] is None
    assert "data_cutoff_at" not in body["results"][0]


async def test_catalog_search_rejects_invalid_q_before_provider(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    async def fake_search(**kwargs):
        raise AssertionError("No debe consultar embeddings con q invalido.")

    monkeypatch.setattr(main, "catalog_search_with_platform_loop", fake_search)
    main.app.state.settings = DummySettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/v2/catalog/search", params={"q": "  ab  "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_catalog_search_rejects_k_above_25_without_clipping(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    async def fake_search(**kwargs):
        raise AssertionError("No debe recortar k ni consultar embeddings.")

    monkeypatch.setattr(main, "catalog_search_with_platform_loop", fake_search)
    main.app.state.settings = DummySettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(
            "/v2/catalog/search",
            params={"q": "desercion escolar", "k": 999},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "1 y 25" in body["error"]["message_dev"]
