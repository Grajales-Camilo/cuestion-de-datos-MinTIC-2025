"""Contrato HTTP de T-306 sin depender de PostgreSQL real."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from app.agent.retention_sweep import RetentionCounts, RetentionSweepSummary


def _settings():
    return SimpleNamespace(
        admin_token=SecretStr("correct-token"),
        sqlalchemy_database_url="postgresql+psycopg://usuario:clave@localhost:5432/no_db",
        psycopg_database_url="postgresql://usuario:clave@localhost:5432/no_db",
        retention_user_days=90,
        retention_eval_months=24,
        retention_tech_months=12,
        retention_hash_salt=SecretStr("test-retention-hash-salt-32-bytes"),
    )


async def test_retention_admin_requires_valid_token_and_returns_contract(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    main.app.state.settings = _settings()
    summary = RetentionSweepSummary(
        already_running=False,
        planned=RetentionCounts(user_runs=2, eval_runs=1, technical_metrics=3),
        executed=RetentionCounts(user_runs=2, eval_runs=1, technical_metrics=3),
    )

    async def run_sweep(*_args, **_kwargs):
        return summary

    monkeypatch.setattr(main, "_run_retention_sweep_with_platform_loop", run_sweep)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        without_token = await client.post("/v2/admin/retention/run")
        invalid_token = await client.post(
            "/v2/admin/retention/run", headers={"X-Admin-Token": "wrong-token"}
        )
        accepted = await client.post(
            "/v2/admin/retention/run", headers={"X-Admin-Token": "correct-token"}
        )

    assert without_token.status_code == 401
    assert invalid_token.status_code == 401
    assert accepted.status_code == 202
    assert accepted.json() == {
        "status": "accepted",
        "reason": None,
        "planned": {"user_runs": 2, "eval_runs": 1, "technical_metrics": 3},
        "executed": {"user_runs": 2, "eval_runs": 1, "technical_metrics": 3},
    }


async def test_retention_admin_reports_already_running(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    import app.main as main

    main.app.state.settings = _settings()
    summary = RetentionSweepSummary(
        already_running=True,
        planned=RetentionCounts(),
        executed=RetentionCounts(),
    )

    async def run_sweep(*_args, **_kwargs):
        return summary

    monkeypatch.setattr(main, "_run_retention_sweep_with_platform_loop", run_sweep)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/v2/admin/retention/run", headers={"X-Admin-Token": "correct-token"}
        )

    assert response.status_code == 202
    assert response.json()["status"] == "skipped"
    assert response.json()["reason"] == "already_running"
