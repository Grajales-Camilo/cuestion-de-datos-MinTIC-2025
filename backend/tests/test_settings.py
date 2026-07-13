import pytest
from pydantic import ValidationError

from app.config import Settings


def settings(**overrides: object) -> Settings:
    """`_env_file=None` aísla la prueba del `.env` local real (mismo hallazgo
    del agente evaluador que en `test_llm_factory.py::settings`; ver ese
    docstring para el detalle) -- aquí ningún test actual depende todavía de
    una clave de proveedor, pero es la misma clase de bug latente."""
    values = {
        "DATABASE_URL": "postgresql://usuario:clave@localhost:5432/cuestion_de_datos",
        "SOCRATA_APP_TOKEN": "token-local",
        "RETENTION_HASH_SALT": "replace-with-local-development-salt-32-bytes",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_normalization_for_sqlalchemy_and_psycopg() -> None:
    loaded = settings(DATABASE_URL="postgres://usuario:clave@localhost:5432/cuestion_de_datos")

    assert loaded.sqlalchemy_database_url.startswith("postgresql+psycopg://")
    assert loaded.psycopg_database_url.startswith("postgresql://")
    assert "clave" in loaded.sqlalchemy_database_url


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///local.db",
        "postgresql://usuario:clave@localhost:5432",
        "postgresql:///cuestion_de_datos",
    ],
)
def test_database_url_rejects_invalid_values(database_url: str) -> None:
    with pytest.raises(ValidationError):
        settings(DATABASE_URL=database_url)


def test_embedding_model_can_be_pending_before_t205() -> None:
    loaded = settings(EMBEDDING_MODEL="")

    assert loaded.embedding_model is None


def test_cors_rejects_wildcards() -> None:
    with pytest.raises(ValidationError):
        settings(CORS_ALLOWED_ORIGINS="http://localhost:3000,*")


def test_worker_lease_defaults_to_heartbeat_timeout() -> None:
    loaded = settings(RUN_HEARTBEAT_TIMEOUT_S=120)

    assert loaded.worker_lease_ttl_s == 120
