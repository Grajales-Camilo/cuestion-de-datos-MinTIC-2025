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
