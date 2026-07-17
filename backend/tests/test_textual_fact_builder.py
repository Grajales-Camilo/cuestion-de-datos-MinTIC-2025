"""T-615E: constructor y verificador puros de hechos textuales."""

from __future__ import annotations

import socket
import uuid
from dataclasses import replace

import pytest

from app.quality.grounded_facts import (
    CategorySelectionParams,
    EmptyTextualFactOperationParams,
    ExtremumLabelParams,
    TextualFactOperation,
    ValuePresenceParams,
)
from app.quality.textual_fact_builder import (
    TEXTUAL_FACT_TEMPLATES,
    TextualEvidenceSnapshot,
    TextualFactError,
    build_textual_fact,
    verify_textual_fact,
)
from app.quality.textual_facts import TextualFactSpec, evaluate_textual_operation

RUN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
EVIDENCE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
FACT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
DATASET_ID = "abcd-1234"


def snapshot(
    rows: tuple[dict[str, object], ...] = ({"label": "  Medellín  "},),
    *,
    run_id: uuid.UUID = RUN_ID,
    evidence_id: uuid.UUID = EVIDENCE_ID,
    dataset_id: str = DATASET_ID,
    eligibility_status: str = "eligible",
    quality_classification: str = "alta",
    canonical_soql: str = "SELECT label LIMIT 1000 OFFSET 0",
    validated_order_is_total: bool = False,
) -> TextualEvidenceSnapshot:
    return TextualEvidenceSnapshot(
        run_id=run_id,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        canonical_soql=canonical_soql,
        rows=rows,
        eligibility_status=eligibility_status,  # type: ignore[arg-type]
        quality_classification=quality_classification,  # type: ignore[arg-type]
        validated_order_is_total=validated_order_is_total,
    )


def spec(
    operation: TextualFactOperation = TextualFactOperation.DIRECT_TEXT,
    *,
    indexes: tuple[int, ...] = (0,),
    columns: tuple[str, ...] = ("label",),
    params=None,
) -> TextualFactSpec:
    if params is None:
        params = EmptyTextualFactOperationParams()
    return TextualFactSpec(
        operation=operation,
        source_row_indexes=indexes,
        columns=columns,
        operation_params=params,
    )


def build(
    source: TextualEvidenceSnapshot | None = None,
    fact_spec: TextualFactSpec | object | None = None,
):
    return build_textual_fact(
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        dataset_id=DATASET_ID,
        snapshot=source if source is not None else snapshot(),
        spec=fact_spec if fact_spec is not None else spec(),  # type: ignore[arg-type]
        fact_id_factory=lambda: FACT_ID,
    )


def assert_error(code: str, callback) -> TextualFactError:
    with pytest.raises(TextualFactError) as captured:
        callback()
    assert captured.value.code == code
    return captured.value


@pytest.mark.parametrize(
    ("source", "fact_spec", "expected_text", "expected_display"),
    [
        (
            snapshot(),
            spec(),
            "El valor observado es Medellín.",
            "Medellín",
        ),
        (
            snapshot(({"label": "Rural"}, {"label": "Urbano"})),
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                indexes=(0, 1),
                params=ValuePresenceParams(
                    target_raw=" rural ",
                    target_normalized="rural",
                ),
            ),
            "El valor Rural está presente.",
            "Rural",
        ),
        (
            snapshot(({"label": "Activo"}, {"label": "ACTIVO"})),
            spec(
                TextualFactOperation.CATEGORY_SELECTION,
                indexes=(0, 1),
                params=CategorySelectionParams(rule="unique_normalized_value"),
            ),
            "La categoría seleccionada es ACTIVO.",
            "ACTIVO",
        ),
        (
            snapshot(
                (
                    {"label": "Medellín", "metric": 2},
                    {"label": "Bogotá", "metric": 5},
                )
            ),
            spec(
                TextualFactOperation.ARGMAX_LABEL,
                indexes=(0, 1),
                columns=("label", "metric"),
                params=ExtremumLabelParams(
                    label_column="label",
                    metric_column="metric",
                ),
            ),
            "La etiqueta con el valor máximo es Bogotá.",
            "Bogotá",
        ),
        (
            snapshot(
                (
                    {"label": "Medellín", "metric": 2},
                    {"label": "Bogotá", "metric": 5},
                )
            ),
            spec(
                TextualFactOperation.ARGMIN_LABEL,
                indexes=(0, 1),
                columns=("label", "metric"),
                params=ExtremumLabelParams(
                    label_column="label",
                    metric_column="metric",
                ),
            ),
            "La etiqueta con el valor mínimo es Medellín.",
            "Medellín",
        ),
        (
            snapshot(
                (
                    {"label": "Bogotá"},
                    {"label": "medellín"},
                    {"label": "BOGOTÁ"},
                )
            ),
            spec(
                TextualFactOperation.CANONICAL_TEXT_SET,
                indexes=(2, 0, 1),
            ),
            "Los valores observados son BOGOTÁ; medellín.",
            "BOGOTÁ; medellín",
        ),
    ],
)
def test_builds_and_independently_verifies_all_six_operations(
    source: TextualEvidenceSnapshot,
    fact_spec: TextualFactSpec,
    expected_text: str,
    expected_display: str,
) -> None:
    fact = build(source, fact_spec)

    assert fact.fact_id == FACT_ID
    assert fact.fact_kind == "textual"
    assert fact.fact == expected_text
    assert fact.display_value == expected_display
    verified = verify_textual_fact(
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        dataset_id=DATASET_ID,
        snapshot=source,
        spec=fact_spec,
        fact=fact,
    )
    assert verified.fact == fact


def test_templates_are_closed_exact_and_cover_only_the_six_operations() -> None:
    assert dict(TEXTUAL_FACT_TEMPLATES) == {
        TextualFactOperation.DIRECT_TEXT: "El valor observado es {display_value}.",
        TextualFactOperation.VALUE_PRESENCE: "El valor {display_value} está presente.",
        TextualFactOperation.CATEGORY_SELECTION: ("La categoría seleccionada es {display_value}."),
        TextualFactOperation.ARGMAX_LABEL: ("La etiqueta con el valor máximo es {display_value}."),
        TextualFactOperation.ARGMIN_LABEL: ("La etiqueta con el valor mínimo es {display_value}."),
        TextualFactOperation.CANONICAL_TEXT_SET: ("Los valores observados son {display_value}."),
    }


def test_preserves_raw_graphy_and_inserts_display_value_literally() -> None:
    raw = "  Medellín {D.C.} ¡sí!  "
    fact = build(snapshot(({"label": raw},)))

    assert fact.raw_values == (raw,)
    assert fact.normalized_values == ("medellín {d.c.} ¡sí!",)
    assert fact.display_value == "Medellín {D.C.} ¡sí!"
    assert fact.fact == "El valor observado es Medellín {D.C.} ¡sí!."


def test_source_hash_is_the_exact_independent_t615d_recomputation() -> None:
    source = snapshot()
    fact_spec = spec()
    fact = build(source, fact_spec)
    independently_recomputed = evaluate_textual_operation(
        evidence=source.to_operation_evidence(),
        spec=fact_spec,
    )

    assert fact.source_hash == independently_recomputed.source_hash


def test_snapshot_defensively_preserves_the_original_rows() -> None:
    mutable_row = {"label": "Medellín"}
    source = snapshot((mutable_row,))
    mutable_row["label"] = "Bogotá"

    assert build(source).display_value == "Medellín"
    with pytest.raises(TypeError):
        source.rows[0]["label"] = "Cali"  # type: ignore[index]


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (None, "textual_evidence_not_found"),
        (
            snapshot(run_id=uuid.uuid4()),
            "textual_evidence_run_mismatch",
        ),
        (
            snapshot(evidence_id=uuid.uuid4()),
            "textual_evidence_mismatch",
        ),
        (
            snapshot(dataset_id="zzzz-9999"),
            "textual_dataset_mismatch",
        ),
        (
            snapshot(eligibility_status="blocked"),
            "textual_evidence_blocked",
        ),
        (
            snapshot(eligibility_status="diagnostic_only"),
            "textual_evidence_diagnostic_only",
        ),
        (
            snapshot(quality_classification="no_recomendada"),
            "textual_evidence_not_recommended",
        ),
        (
            snapshot(rows=()),
            "textual_evidence_rows_unverifiable",
        ),
    ],
)
def test_rejects_inexistent_mismatched_or_non_deliverable_evidence(
    source: TextualEvidenceSnapshot | None,
    code: str,
) -> None:
    assert_error(
        code,
        lambda: build_textual_fact(
            run_id=RUN_ID,
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=source,
            spec=spec(),
            fact_id_factory=lambda: FACT_ID,
        ),
    )


@pytest.mark.parametrize(
    ("source", "fact_spec", "code"),
    [
        (
            snapshot(),
            spec(indexes=(1,)),
            "textual_invalid_row_index",
        ),
        (
            snapshot(),
            spec(columns=("missing",)),
            "textual_missing_column",
        ),
        (
            snapshot(({"label": None},)),
            spec(),
            "textual_null_value",
        ),
        (
            snapshot(({"label": " \t"},)),
            spec(),
            "textual_empty_value",
        ),
        (
            snapshot(({"label": "Activo"}, {"label": "Inactivo"})),
            spec(
                TextualFactOperation.CATEGORY_SELECTION,
                indexes=(0, 1),
                params=CategorySelectionParams(rule="unique_normalized_value"),
            ),
            "textual_ambiguous_category",
        ),
        (
            snapshot(
                (
                    {"label": "A", "metric": 5},
                    {"label": "B", "metric": 5},
                )
            ),
            spec(
                TextualFactOperation.ARGMAX_LABEL,
                indexes=(0, 1),
                columns=("label", "metric"),
                params=ExtremumLabelParams(
                    label_column="label",
                    metric_column="metric",
                ),
            ),
            "textual_extremum_tie",
        ),
        (
            snapshot(),
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                params=EmptyTextualFactOperationParams(),
            ),
            "textual_invalid_operation_params",
        ),
    ],
)
def test_translates_t615d_rejections_to_stable_builder_errors(
    source: TextualEvidenceSnapshot,
    fact_spec: TextualFactSpec,
    code: str,
) -> None:
    assert_error(code, lambda: build(source, fact_spec))


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"fact_kind": "quantitative"}, "textual_fact_kind_mismatch"),
        ({"evidence_id": uuid.uuid4()}, "textual_evidence_mismatch"),
        ({"dataset_id": "zzzz-9999"}, "textual_dataset_mismatch"),
        ({"operation": "canonical_text_set"}, "textual_operation_mismatch"),
        ({"source_row_indexes": (1,)}, "textual_source_rows_mismatch"),
        ({"columns": ("other",)}, "textual_columns_mismatch"),
        ({"raw_values": ("Bogotá",)}, "textual_raw_values_mismatch"),
        ({"normalized_values": ("bogotá",)}, "textual_normalized_values_mismatch"),
        ({"display_value": "Bogotá"}, "textual_display_value_mismatch"),
        (
            {"normalization_profile": "text-es-v2"},
            "textual_normalization_profile_mismatch",
        ),
        (
            {
                "operation_params": ValuePresenceParams(
                    target_raw="Medellín",
                    target_normalized="medellín",
                )
            },
            "textual_operation_params_mismatch",
        ),
        ({"algorithm_version": "textual-fact-v2"}, "textual_algorithm_version_mismatch"),
        (
            {"source_hash": f"sha256-jcs-v1:{'f' * 64}"},
            "textual_source_hash_mismatch",
        ),
        ({"fact": "Texto factual alterado."}, "textual_fact_text_mismatch"),
    ],
)
def test_verifier_rejects_every_tampered_material_field(
    changes: dict[str, object],
    code: str,
) -> None:
    source = snapshot()
    fact_spec = spec()
    tampered = build(source, fact_spec).model_copy(update=changes)

    assert_error(
        code,
        lambda: verify_textual_fact(
            run_id=RUN_ID,
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=source,
            spec=fact_spec,
            fact=tampered,
        ),
    )


def test_verifier_rejects_run_mismatch_before_recomputation() -> None:
    source = snapshot()
    fact = build(source)
    assert_error(
        "textual_evidence_run_mismatch",
        lambda: verify_textual_fact(
            run_id=uuid.uuid4(),
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=source,
            spec=spec(),
            fact=fact,
        ),
    )


@pytest.mark.parametrize(
    "quantitative_substitute",
    [
        {"operation": "count", "count": 1},
        {"claim_type": "direct", "raw_value": 1},
        {"formula": {"const": 1}, "unit": None, "rounding": 0},
    ],
)
def test_rejects_count_one_or_other_quantitative_substitutes(
    quantitative_substitute: dict[str, object],
) -> None:
    assert_error(
        "textual_quantitative_substitute",
        lambda: build(snapshot(), quantitative_substitute),
    )


def test_pure_builder_does_not_call_network_llm_or_postgresql(monkeypatch) -> None:
    def forbidden_network(*args, **kwargs):
        raise AssertionError("la prueba pura intentó abrir red")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    source = snapshot()
    fact = build(source)
    assert (
        verify_textual_fact(
            run_id=RUN_ID,
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=source,
            spec=spec(),
            fact=fact,
        ).fact
        == fact
    )


def test_verifier_uses_the_original_spec_not_fields_reconstructed_from_fact() -> None:
    source = snapshot(({"label": "Medellín"}, {"label": "Bogotá"}))
    direct_spec = spec()
    fact = build(source, direct_spec)
    other_spec = replace(
        direct_spec,
        operation=TextualFactOperation.CANONICAL_TEXT_SET,
        source_row_indexes=(0, 1),
    )

    assert_error(
        "textual_operation_mismatch",
        lambda: verify_textual_fact(
            run_id=RUN_ID,
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=source,
            spec=other_spec,
            fact=fact,
        ),
    )


@pytest.mark.parametrize(
    "changed_source",
    [
        snapshot(({"label": "Bogotá"},)),
        snapshot(canonical_soql="SELECT label LIMIT 1 OFFSET 0"),
    ],
)
def test_verifier_rejects_when_the_frozen_source_material_changes(
    changed_source: TextualEvidenceSnapshot,
) -> None:
    original = snapshot()
    fact_spec = spec()
    fact = build(original, fact_spec)

    with pytest.raises(TextualFactError) as captured:
        verify_textual_fact(
            run_id=RUN_ID,
            evidence_id=EVIDENCE_ID,
            dataset_id=DATASET_ID,
            snapshot=changed_source,
            spec=fact_spec,
            fact=fact,
        )
    assert captured.value.code in {
        "textual_raw_values_mismatch",
        "textual_source_hash_mismatch",
    }
