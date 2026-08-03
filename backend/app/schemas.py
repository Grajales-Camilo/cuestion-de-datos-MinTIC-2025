from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.quality.grounded_facts import (
    QuantitativeClaimResponse as QuantitativeClaimResponse,
)
from app.quality.grounded_facts import (
    TextNormalizationProfile,
    TextualFactAlgorithmVersion,
    TextualFactKind,
    TextualFactOperation,
    TextualFactOperationParams,
)
from app.quality.grounded_facts import (
    TextualFact as InternalTextualFact,
)


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
    context_hint: str | None = Field(default=None, max_length=2000)
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


class TextualFactResponse(BaseModel):
    """Forma pública cerrada de un hecho textual verificado (RF-210)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: UUID
    fact_kind: Literal[TextualFactKind.TEXTUAL] = TextualFactKind.TEXTUAL
    fact: str = Field(min_length=1)
    operation: TextualFactOperation
    evidence_id: UUID
    dataset_id: str = Field(pattern=r"^[a-z0-9]{4}-[a-z0-9]{4}$")
    source_row_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(
        min_length=1,
        max_length=100,
    )
    columns: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    raw_values: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1,
        max_length=50,
    )
    normalized_values: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1,
        max_length=50,
    )
    display_value: str = Field(min_length=1)
    normalization_profile: Literal[TextNormalizationProfile.TEXT_ES_V1] = (
        TextNormalizationProfile.TEXT_ES_V1
    )
    operation_params: TextualFactOperationParams
    algorithm_version: Literal[TextualFactAlgorithmVersion.TEXTUAL_FACT_V1] = (
        TextualFactAlgorithmVersion.TEXTUAL_FACT_V1
    )
    source_hash: str = Field(pattern=r"^sha256-jcs-v1:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_public_shape(self) -> TextualFactResponse:
        # Reutiliza las invariantes tipadas del dominio sin exponer su modelo
        # ni convertirlo en la representación pública.
        InternalTextualFact.model_validate(self.model_dump())
        return self


_TEXTUAL_FACT_LIST = TypeAdapter(list[TextualFactResponse])


def materialize_textual_fact_fields(
    payload: dict[str, Any],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    """Frontera aditiva de lectura para payloads terminales T-615G.

    Crea una copia, valida cualquier hecho explícito y materializa listas
    vacías en históricos anteriores. Nunca infiere hechos ni reescribe el
    JSON persistido.
    """

    materialized = dict(payload)
    textual_facts = _TEXTUAL_FACT_LIST.validate_python(materialized.get("textual_facts", []))
    partial_textual_facts = _TEXTUAL_FACT_LIST.validate_python(
        materialized.get("partial_textual_facts", [])
    )
    terminal_status = status or materialized.get("status")

    if terminal_status in {"no_evidence", "failed"}:
        textual_facts = []
        partial_textual_facts = []
    elif terminal_status == "interrupted":
        textual_facts = []
    elif terminal_status == "completed":
        partial_textual_facts = []

    materialized["textual_facts"] = _TEXTUAL_FACT_LIST.dump_python(textual_facts, mode="json")
    materialized["partial_textual_facts"] = _TEXTUAL_FACT_LIST.dump_python(
        partial_textual_facts, mode="json"
    )
    return materialized


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["running"]
    steps: list[dict[str, Any]]
    events: list[dict[str, Any]]
    last_event_seq: int
    partial_evidence: list[dict[str, Any]]
    partial_claims: list[dict[str, Any]]
    partial_textual_facts: list[TextualFactResponse] = Field(default_factory=list)
    usage: RunUsage


class RunResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["completed", "no_evidence", "interrupted", "failed"]
    answer: dict[str, Any]
    textual_facts: list[TextualFactResponse] = Field(default_factory=list)
    partial_textual_facts: list[TextualFactResponse] = Field(default_factory=list)
    steps: list[dict[str, Any]]
    events: list[dict[str, Any]]
    last_event_seq: int
