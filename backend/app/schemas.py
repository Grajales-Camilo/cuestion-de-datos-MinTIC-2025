from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.quality.grounded_facts import QuantitativeClaimResponse as QuantitativeClaimResponse


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


# T-304 / RF-201, RF-204, RF-801: estos modelos son el contrato publico de
# las corridas. El token solo aparece en AgentQueryResponse.
class AgentQueryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int | None = Field(default=None, ge=1, le=25)
    llm_provider: Literal["google", "anthropic"] | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=10, max_length=2000)
    context_hint: str | None = Field(default=None, max_length=1000)
    options: AgentQueryOptions | None = None


class AgentQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_access_token: str
    token_expires_at: datetime
    stream_url: str


class RunUsage(BaseModel):
    steps_used: int | None = None
    latency_ms: int | None = None
    estimated_cost_usd: float | None = None
    termination_reason: str | None = None


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["running"]
    steps: list[dict[str, Any]]
    events: list[dict[str, Any]]
    last_event_seq: int
    partial_evidence: list[dict[str, Any]]
    partial_claims: list[dict[str, Any]]
    usage: RunUsage


class RunResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["completed", "no_evidence", "interrupted", "failed"]
    answer: dict[str, Any]
    steps: list[dict[str, Any]]
    events: list[dict[str, Any]]
    last_event_seq: int
