from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AnyUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PostgresScheme = Literal["postgresql", "postgres"]
LLMProvider = Literal["google", "anthropic"]
AgentRuntime = Literal["deterministic", "legacy"]


class Settings(BaseSettings):
    """Configuracion del backend para RF-206, RF-702, RF-703, RF-804 y RNF-011."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    socrata_app_token: SecretStr | None = Field(default=None, alias="SOCRATA_APP_TOKEN")
    llm_provider: LLMProvider = Field(default="google", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")
    agent_runtime: AgentRuntime = Field(default="deterministic", alias="AGENT_RUNTIME")
    embedding_model: str | None = Field(default=None, alias="EMBEDDING_MODEL")
    # research.md §19 (2026-07-12): el camino feliz sin errores consume
    # exactamente 10 pasos, dejando 0 margen para el retry de claim_builder
    # (o cualquier otra reparacion) ya implementado en el grafo. 14 deja
    # espacio real para una ronda completa de reparacion (+3) mas 1 paso
    # de margen adicional, sin tocar el limite configurable de 1..25.
    agent_max_steps: Annotated[int, Field(ge=1, le=25)] = Field(default=14, alias="AGENT_MAX_STEPS")
    run_max_duration_s: Annotated[int, Field(gt=0)] = Field(default=600, alias="RUN_MAX_DURATION_S")
    run_heartbeat_timeout_s: Annotated[int, Field(gt=0)] = Field(
        default=120, alias="RUN_HEARTBEAT_TIMEOUT_S"
    )
    worker_lease_ttl_s: int | None = Field(default=None, alias="WORKER_LEASE_TTL_S")
    delete_active_grace_s: Annotated[int, Field(ge=0, le=30)] = Field(
        default=5, alias="DELETE_ACTIVE_GRACE_S"
    )
    retention_user_days: Annotated[int, Field(gt=0)] = Field(
        default=90, alias="RETENTION_USER_DAYS"
    )
    retention_eval_months: Annotated[int, Field(gt=0)] = Field(
        default=24, alias="RETENTION_EVAL_MONTHS"
    )
    retention_tech_months: Annotated[int, Field(gt=0)] = Field(
        default=12, alias="RETENTION_TECH_MONTHS"
    )
    retention_hash_salt: SecretStr | None = Field(default=None, alias="RETENTION_HASH_SALT")
    catalog_stale_after_days: Annotated[int, Field(gt=0)] = Field(
        default=8, alias="CATALOG_STALE_AFTER_DAYS"
    )
    placeholder_min_ratio: Annotated[float, Field(ge=0, le=1)] = Field(
        default=0.30, alias="PLACEHOLDER_MIN_RATIO"
    )
    max_concurrent_runs: Annotated[int, Field(gt=0)] = Field(default=3, alias="MAX_CONCURRENT_RUNS")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS"
    )
    admin_token: SecretStr | None = Field(default=None, alias="ADMIN_TOKEN")
    eval_mode: bool = Field(default=False, alias="EVAL_MODE")

    @field_validator("embedding_model", mode="before")
    @classmethod
    def empty_embedding_model_is_pending(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, value: object) -> str:
        if isinstance(value, str):
            origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        else:
            raise ValueError("CORS_ALLOWED_ORIGINS debe ser una lista CSV")
        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS debe contener al menos un origen")
        if any(origin == "*" or "*" in origin for origin in origins):
            raise ValueError("CORS_ALLOWED_ORIGINS no permite comodines")
        for origin in origins:
            AnyUrl(origin)
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "Settings":
        if self.worker_lease_ttl_s is None:
            self.worker_lease_ttl_s = self.run_heartbeat_timeout_s
        if self.worker_lease_ttl_s < 30:
            raise ValueError("WORKER_LEASE_TTL_S no puede ser menor a 30")
        if self.worker_lease_ttl_s > self.run_heartbeat_timeout_s:
            raise ValueError("WORKER_LEASE_TTL_S no puede exceder RUN_HEARTBEAT_TIMEOUT_S")
        validate_database_url(self.database_url)
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        return normalize_database_url_for_sqlalchemy(self.database_url)

    @property
    def psycopg_database_url(self) -> str:
        return normalize_database_url_for_psycopg(self.database_url)

    @property
    def llm_provider_configured(self) -> bool:
        if self.llm_provider == "google":
            return bool(self.google_api_key and self.google_api_key.get_secret_value())
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())
        return False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


def validate_database_url(database_url: str) -> None:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgres", "postgresql+psycopg"}:
        raise ValueError("DATABASE_URL debe usar postgresql:// o postgres://")
    if not parsed.hostname:
        raise ValueError("DATABASE_URL debe incluir host")
    if not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL debe incluir nombre de base de datos")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("sslmode") == "disable" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("DATABASE_URL no puede usar sslmode=disable fuera de localhost")


def normalize_database_url_for_sqlalchemy(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = "postgresql+psycopg"
    query = urlencode(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunsplit((scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def normalize_database_url_for_psycopg(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme: PostgresScheme = "postgresql"
    query = urlencode(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunsplit((scheme, parsed.netloc, parsed.path, query, parsed.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
