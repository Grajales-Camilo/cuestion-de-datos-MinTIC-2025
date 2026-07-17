"""Contrato público aditivo de hechos textuales (T-615G, RF-210/RF-801)."""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas import TextualFactResponse, materialize_textual_fact_fields


def _textual_fact(**overrides: object) -> dict[str, object]:
    fact: dict[str, object] = {
        "fact_id": str(uuid.UUID("10000000-0000-0000-0000-000000000001")),
        "fact_kind": "textual",
        "fact": "La ciudad es Medellín.",
        "operation": "direct_text",
        "evidence_id": str(uuid.UUID("20000000-0000-0000-0000-000000000002")),
        "dataset_id": "abcd-1234",
        "source_row_indexes": [0],
        "columns": ["ciudad"],
        "raw_values": ["  Medellín  "],
        "normalized_values": ["medellín"],
        "display_value": "Medellín",
        "normalization_profile": "text-es-v1",
        "operation_params": {},
        "algorithm_version": "textual-fact-v1",
        "source_hash": f"sha256-jcs-v1:{'a' * 64}",
    }
    fact.update(overrides)
    return fact


def test_textual_fact_response_is_closed_and_rejects_unknown_operation() -> None:
    validated = TextualFactResponse.model_validate(_textual_fact())
    assert validated.raw_values == ("  Medellín  ",)

    with pytest.raises(ValidationError):
        TextualFactResponse.model_validate(_textual_fact(extra_internal="forbidden"))
    with pytest.raises(ValidationError):
        TextualFactResponse.model_validate(_textual_fact(operation="invented"))


def test_historical_answer_without_textual_fields_materializes_empty_lists_without_mutation() -> (
    None
):
    historical = {
        "status": "completed",
        "claims": [{"raw_value": 1, "description": "No es un hecho textual"}],
    }
    original = json.loads(json.dumps(historical))

    materialized = materialize_textual_fact_fields(historical)

    assert materialized["textual_facts"] == []
    assert materialized["partial_textual_facts"] == []
    assert historical == original
    assert materialized["claims"] == historical["claims"]


@pytest.mark.parametrize("status", ["no_evidence", "failed"])
def test_non_deliverable_terminal_states_never_expose_textual_facts(status: str) -> None:
    materialized = materialize_textual_fact_fields(
        {
            "status": status,
            "textual_facts": [_textual_fact()],
            "partial_textual_facts": [_textual_fact()],
        }
    )

    assert materialized["textual_facts"] == []
    assert materialized["partial_textual_facts"] == []


def test_interrupted_exposes_only_explicit_persisted_partials() -> None:
    materialized = materialize_textual_fact_fields(
        {
            "status": "interrupted",
            "textual_facts": [_textual_fact()],
            "partial_textual_facts": [_textual_fact()],
        }
    )

    assert materialized["textual_facts"] == []
    assert materialized["partial_textual_facts"] == [_textual_fact()]


def test_invalid_textual_fact_is_rejected_instead_of_inferred() -> None:
    with pytest.raises(ValidationError):
        materialize_textual_fact_fields(
            {"status": "completed", "textual_facts": [{"raw_value": 1}]}
        )


def test_openapi_change_is_limited_to_authorized_additive_surface() -> None:
    schemas = app.openapi()["components"]["schemas"]
    result = schemas["RunResultResponse"]
    running = schemas["RunStatusResponse"]

    assert schemas["TextualFactResponse"]["additionalProperties"] is False
    assert result["properties"]["textual_facts"]["items"] == {
        "$ref": "#/components/schemas/TextualFactResponse"
    }
    assert result["properties"]["partial_textual_facts"]["items"] == {
        "$ref": "#/components/schemas/TextualFactResponse"
    }
    assert running["properties"]["partial_claims"] == {
        "items": {"additionalProperties": True, "type": "object"},
        "title": "Partial Claims",
        "type": "array",
    }
    assert result["properties"]["answer"] == {
        "additionalProperties": True,
        "title": "Answer",
        "type": "object",
    }
