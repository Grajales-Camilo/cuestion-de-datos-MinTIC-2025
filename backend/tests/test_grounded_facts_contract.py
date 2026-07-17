"""Contrato estructural T-615B (RF-210) sin DB, red ni integración productiva."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from app.quality.grounded_facts import (
    GroundedFact,
    GroundedSynthesisPlan,
    QuantitativeClaim,
    QuantitativeClaimResponse,
    TextNormalizationProfile,
    TextualFact,
    TextualFactAlgorithmVersion,
    TextualFactKind,
    TextualFactOperation,
)

CLAIM_ID = "11111111-1111-4111-8111-111111111111"
FACT_ID = "22222222-2222-4222-8222-222222222222"
EVIDENCE_ID = "33333333-3333-4333-8333-333333333333"
SECOND_FACT_ID = "44444444-4444-4444-8444-444444444444"


def quantitative_payload() -> dict[str, object]:
    return {
        "claim_id": CLAIM_ID,
        "claim": "La tasa observada fue 8,4 %.",
        "claim_type": "derived",
        "evidence_id": EVIDENCE_ID,
        "dataset_id": "abcd-1234",
        "source_row_indexes": [0, 1],
        "columns": ["matriculados", "desertores"],
        "formula": {
            "op": "div",
            "args": [{"col": "desertores"}, {"col": "matriculados"}],
        },
        "raw_value": 8.3721,
        "display_value": "8,4 %",
        "unit": "%",
        "rounding": 1,
        "source_hash": f"sha256:{'a' * 64}",
    }


def textual_payload(operation: str = "direct_text") -> dict[str, object]:
    payload: dict[str, object] = {
        "fact_id": FACT_ID,
        "fact_kind": "textual",
        "fact": "El municipio observado es Medellín.",
        "operation": operation,
        "evidence_id": EVIDENCE_ID,
        "dataset_id": "abcd-1234",
        "source_row_indexes": [0],
        "columns": ["municipio"],
        "raw_values": ["Medellín"],
        "normalized_values": ["medellín"],
        "display_value": "Medellín",
        "normalization_profile": "text-es-v1",
        "operation_params": {},
        "algorithm_version": "textual-fact-v1",
        "source_hash": f"sha256-jcs-v1:{'b' * 64}",
    }
    if operation == "value_presence":
        payload.update(
            source_row_indexes=[0, 1],
            operation_params={
                "target_raw": "Medellín",
                "target_normalized": "medellín",
            },
        )
    elif operation == "category_selection":
        payload["operation_params"] = {"rule": "unique_normalized_value"}
    elif operation in {"argmax_label", "argmin_label"}:
        payload.update(
            source_row_indexes=[0, 1],
            columns=["municipio", "total"],
            operation_params={
                "label_column": "municipio",
                "metric_column": "total",
                "tie_policy": "reject",
            },
        )
    elif operation == "canonical_text_set":
        payload.update(
            source_row_indexes=[0, 1],
            raw_values=["Bogotá", "Medellín"],
            normalized_values=["bogotá", "medellín"],
            display_value="Bogotá; Medellín",
        )
    return payload


@pytest.mark.parametrize("operation", [item.value for item in TextualFactOperation])
def test_accepts_the_six_closed_textual_operations(operation: str) -> None:
    fact = TextualFact.model_validate(textual_payload(operation))

    assert fact.operation.value == operation
    assert fact.fact_kind is TextualFactKind.TEXTUAL


def test_rejects_unknown_operation_profile_version_kind_and_hash() -> None:
    invalid_values = (
        ("operation", "free_text"),
        ("normalization_profile", "text-es-v2"),
        ("algorithm_version", "textual-fact-v2"),
        ("fact_kind", "quantitative"),
        ("source_hash", f"sha256:{'b' * 64}"),
        ("source_hash", f"sha256-jcs-v1:{'B' * 64}"),
    )
    for field, value in invalid_values:
        payload = textual_payload()
        payload[field] = value
        with pytest.raises(ValidationError):
            TextualFact.model_validate(payload)


def test_only_frozen_initial_profile_and_algorithm_values_exist() -> None:
    assert [item.value for item in TextNormalizationProfile] == ["text-es-v1"]
    assert [item.value for item in TextualFactAlgorithmVersion] == ["textual-fact-v1"]


def test_rejects_missing_and_extra_fields_in_closed_models() -> None:
    missing = textual_payload()
    del missing["display_value"]
    with pytest.raises(ValidationError, match="display_value"):
        TextualFact.model_validate(missing)

    extra = textual_payload()
    extra["free_text"] = "campo no contractual"
    with pytest.raises(ValidationError, match="Extra inputs"):
        TextualFact.model_validate(extra)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_row_indexes", []),
        ("source_row_indexes", [-1]),
        ("source_row_indexes", [0, 0]),
        ("source_row_indexes", [1, 0]),
        ("columns", []),
        ("columns", ["municipio", "municipio"]),
        ("raw_values", []),
        ("normalized_values", []),
        ("normalized_values", ["medellín", "bogotá"]),
    ],
)
def test_rejects_structurally_invalid_indexes_and_collections(
    field: str,
    value: object,
) -> None:
    payload = textual_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        TextualFact.model_validate(payload)


def test_rejects_operation_params_and_cardinalities_that_do_not_match_operation() -> None:
    wrong_params = textual_payload("direct_text")
    wrong_params["operation_params"] = {
        "target_raw": "Medellín",
        "target_normalized": "medellín",
    }
    with pytest.raises(ValidationError, match="operation_params"):
        TextualFact.model_validate(wrong_params)

    too_many_rows = textual_payload("direct_text")
    too_many_rows["source_row_indexes"] = [0, 1]
    with pytest.raises(ValidationError, match="exactamente un índice"):
        TextualFact.model_validate(too_many_rows)

    wrong_extremum_columns = textual_payload("argmax_label")
    wrong_extremum_columns["columns"] = ["total", "municipio"]
    with pytest.raises(ValidationError, match="label_column"):
        TextualFact.model_validate(wrong_extremum_columns)

    invalid_tie_policy = textual_payload("argmin_label")
    params = deepcopy(invalid_tie_policy["operation_params"])
    assert isinstance(params, dict)
    params["tie_policy"] = "first"
    invalid_tie_policy["operation_params"] = params
    with pytest.raises(ValidationError, match="reject"):
        TextualFact.model_validate(invalid_tie_policy)


def test_grounded_fact_discriminator_selects_quantitative_or_textual_variant() -> None:
    adapter = TypeAdapter(GroundedFact)
    quantitative = adapter.validate_python({"fact_kind": "quantitative", **quantitative_payload()})
    textual = adapter.validate_python(textual_payload())

    assert isinstance(quantitative, QuantitativeClaim)
    assert isinstance(textual, TextualFact)


def test_grounded_fact_rejects_missing_unknown_or_incomplete_discriminator_shape() -> None:
    adapter = TypeAdapter(GroundedFact)
    with pytest.raises(ValidationError):
        adapter.validate_python(quantitative_payload())
    with pytest.raises(ValidationError):
        adapter.validate_python({"fact_kind": "unknown", **quantitative_payload()})
    with pytest.raises(ValidationError):
        adapter.validate_python({"fact_kind": "textual", **quantitative_payload()})


def test_quantitative_public_serialization_remains_exactly_unchanged() -> None:
    expected = quantitative_payload()
    response = QuantitativeClaimResponse.model_validate(expected)
    internal = QuantitativeClaim.model_validate({"fact_kind": "quantitative", **expected})

    assert response.model_dump(mode="json") == expected
    assert internal.to_public_response().model_dump(mode="json") == expected
    assert "fact_kind" not in QuantitativeClaimResponse.model_fields
    assert "claim_kind" not in QuantitativeClaimResponse.model_fields


def test_grounded_synthesis_plan_is_closed_typed_and_checks_reference_counts() -> None:
    valid = {
        "schema_version": "grounded-synthesis-plan-v1",
        "segments": [
            {
                "segment_id": "s1",
                "connector": "sin_conector",
                "template": "comparison_pair",
                "fact_refs": [
                    {"fact_kind": "quantitative", "id": CLAIM_ID},
                    {"fact_kind": "textual", "id": FACT_ID},
                ],
            }
        ],
        "closing": "sin_cierre",
    }
    plan = GroundedSynthesisPlan.model_validate(valid)
    assert plan.model_dump(mode="json") == valid

    incomplete = deepcopy(valid)
    incomplete["segments"][0]["fact_refs"].pop()
    with pytest.raises(ValidationError, match="exactamente 2"):
        GroundedSynthesisPlan.model_validate(incomplete)

    extra = deepcopy(valid)
    extra["free_text"] = "no permitido"
    with pytest.raises(ValidationError, match="Extra inputs"):
        GroundedSynthesisPlan.model_validate(extra)


def test_grounded_synthesis_plan_rejects_duplicate_segments_and_references() -> None:
    segment = {
        "segment_id": "s1",
        "connector": "sin_conector",
        "template": "fact_statement",
        "fact_refs": [{"fact_kind": "textual", "id": FACT_ID}],
    }
    duplicate_segment = deepcopy(segment)
    duplicate_segment["fact_refs"] = [{"fact_kind": "textual", "id": SECOND_FACT_ID}]
    payload = {
        "schema_version": "grounded-synthesis-plan-v1",
        "segments": [segment, duplicate_segment],
        "closing": "advertencia_calidad",
    }
    with pytest.raises(ValidationError, match="segment_id"):
        GroundedSynthesisPlan.model_validate(payload)

    duplicate_reference = deepcopy(segment)
    duplicate_reference["segment_id"] = "s2"
    payload["segments"] = [segment, duplicate_reference]
    with pytest.raises(ValidationError, match="referencia factual"):
        GroundedSynthesisPlan.model_validate(payload)


def test_productive_openapi_does_not_expose_t615b_models() -> None:
    from app.main import app

    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "TextualFact" not in components
    assert "GroundedFact" not in components
    assert "QuantitativeClaimResponse" not in components
