from pydantic import SecretStr


class DummySettings:
    admin_token = SecretStr("correct-token")


async def test_reload_publishers_without_token_is_unauthorized(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    main.app.state.settings = DummySettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/v2/admin/publishers/reload")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "message_user" in body["error"]


async def test_reload_publishers_with_wrong_token_is_unauthorized(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    main.app.state.settings = DummySettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/v2/admin/publishers/reload", headers={"X-Admin-Token": "wrong-token"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_reload_publishers_without_configured_admin_token_is_unauthorized(
    monkeypatch,
) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    class NoAdminTokenSettings:
        admin_token = None

    main.app.state.settings = NoAdminTokenSettings()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/v2/admin/publishers/reload", headers={"X-Admin-Token": "anything"}
        )

    assert response.status_code == 401
