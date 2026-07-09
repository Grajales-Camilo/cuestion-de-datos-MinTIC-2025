from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CatalogIndexCheck(BaseModel):
    status: Literal["ok", "degraded"]
    datasets_indexed: int | None = None
    last_ingest_at: str | None = None
    detail: str | None = None


class LLMProviderCheck(BaseModel):
    status: Literal["ok", "degraded"]
    provider: str
    model: str
    detail: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    checks: dict[str, str | CatalogIndexCheck | LLMProviderCheck | dict[str, Any]]
    version: str


class ErrorDetail(BaseModel):
    code: str
    status: str | None = None
    message_user: str
    message_dev: str | None = None
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    """Sobre de error estandar (contracts/api-rest.md §6). /v2/health es la unica excepcion."""

    error: ErrorDetail


class PublishersReloadSummary(BaseModel):
    publishers_created: int
    publishers_updated: int
    aliases_created: int
    ambiguous_aliases: int


class CatalogSearchResult(BaseModel):
    dataset_id: str
    name: str
    publisher: str | None
    official_publisher_id: str | None
    publisher_verification_status: str
    pii_risk_level: str
    eligibility_status: str
    eligibility_reasons: list[Any]
    similarity: float
    row_count: int | None
    data_updated_at: str | None
    latest_observed_cutoff_at: str | None
    metadata_synced_at: str
    index_stale: bool
    columns_preview: list[str]


class CatalogSearchResponse(BaseModel):
    query: str
    results: list[CatalogSearchResult]
