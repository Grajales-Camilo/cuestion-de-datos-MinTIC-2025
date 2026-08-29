class DummySettings:
    llm_provider = "google"
    llm_model = "gemini-2.5-flash"
    llm_provider_configured = False
    sqlalchemy_database_url = "postgresql+psycopg://usuario:clave@localhost:5432/no_db"


async def test_health_uses_health_response_for_degraded_db(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://usuario:clave@localhost:5432/cuestion_de_datos"
    )
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "token-local")
    monkeypatch.setenv("RETENTION_HASH_SALT", "replace-with-local-development-salt-32-bytes")

    import app.main as main

    database_engine = object()
    observed_databases = []

    async def fake_check_database_and_catalog(database):
        observed_databases.append(database)
        return False, main.CatalogIndexCheck(status="degraded", detail="not_initialized")

    monkeypatch.setattr(main, "check_database_and_catalog", fake_check_database_and_catalog)
    main.app.state.settings = DummySettings()
    main.app.state.database_engine = database_engine

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/v2/health")
        second_response = await client.get("/v2/health")

    assert response.status_code == 503
    assert second_response.status_code == 503
    assert observed_databases == [database_engine, database_engine]
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "degraded"
    assert body["checks"]["catalog_index"]["detail"] == "not_initialized"
    assert "error" not in body
