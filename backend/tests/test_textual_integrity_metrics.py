from __future__ import annotations

from copy import deepcopy

import pytest

from eval.metrics import assess_textual_integrity

FACT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_FACT_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_HASH = f"sha256-jcs-v1:{'a' * 64}"


def _fact(*, fact_id: str = FACT_ID, operation: str = "direct_text") -> dict:
    return {
        "fact_id": fact_id,
        "fact_kind": "textual",
        "fact": "La categoría seleccionada es Salud.",
        "operation": operation,
        "evidence_id": "33333333-3333-4333-8333-333333333333",
        "dataset_id": "abcd-1234",
        "source_row_indexes": [0],
        "columns": ["categoria"],
        "raw_values": ["Salud"],
        "normalized_values": ["salud"],
        "display_value": "Salud",
        "normalization_profile": "text-es-v1",
        "operation_params": {},
        "algorithm_version": "textual-fact-v1",
        "source_hash": SOURCE_HASH,
    }


def _allowed(fact: dict | None = None) -> list[dict]:
    item = fact or _fact()
    return [
        {
            "id": item["fact_id"],
            "run_id": "55555555-5555-4555-8555-555555555555",
            "evidence_id": item["evidence_id"],
            "dataset_id": item["dataset_id"],
            "fact_kind": "textual",
            "source_row_indexes": item["source_row_indexes"],
            "columns": item["columns"],
            "source_hash": item["source_hash"],
            "quality_classification": "alta",
            "fact": item["fact"],
        }
    ]


def _plan(*ids: str) -> dict:
    return {
        "schema_version": "grounded-synthesis-plan-v1",
        "segments": [
            {
                "segment_id": f"s{index}",
                "connector": "sin_conector" if index == 1 else "ademas",
                "template": "fact_statement",
                "fact_refs": [{"fact_kind": "textual", "id": fact_id}],
            }
            for index, fact_id in enumerate(ids, 1)
        ],
        "closing": "sin_cierre",
    }


def _final(*facts: dict, narrative: str = "La categoría seleccionada es Salud.") -> dict:
    return {
        "run_id": "55555555-5555-4555-8555-555555555555",
        "textual_facts": list(facts),
        "narrative": narrative,
    }


def _assess(
    final: dict,
    plan: dict | None,
    allowed: list[dict],
    verified: list[dict] | None = None,
):
    return assess_textual_integrity(
        final,
        plan,
        allowed,
        [_fact()] if verified is None else verified,
    )


def test_textual_integrity_complete_is_reproducible_and_privacy_safe() -> None:
    result = _assess(_final(_fact()), _plan(FACT_ID), _allowed())

    assert result.textual_fact_reference_coverage == 1.0
    assert result.textual_facts_reproducible == 1.0
    assert result.textual_fact_display_match == 1.0
    assert result.orphan_factual_segments_count == 0
    assert result.invalid_textual_operation_count == 0
    assert result.grounded_fact_integrity is True
    assert result.fact_fingerprints == (
        {
            "algorithm_version": "textual-fact-v1",
            "normalization_profile": "text-es-v1",
            "operation": "direct_text",
            "source_hash": SOURCE_HASH,
        },
    )


def test_textual_integrity_detects_incomplete_coverage_and_unknown_reference() -> None:
    second = _fact(fact_id=OTHER_FACT_ID)
    result = _assess(
        _final(_fact(), second),
        _plan(FACT_ID, "44444444-4444-4444-8444-444444444444"),
        _allowed(),
    )

    assert result.textual_fact_reference_coverage == 0.5
    assert result.orphan_factual_segments_count == 1
    assert result.grounded_fact_integrity is False


def test_textual_integrity_detects_hash_and_presentation_only_changes() -> None:
    changed = deepcopy(_fact())
    changed["source_hash"] = f"sha256-jcs-v1:{'b' * 64}"
    hash_result = _assess(_final(changed), _plan(FACT_ID), _allowed())
    display_result = _assess(
        _final(_fact(), narrative="La categoría seleccionada es salud."),
        _plan(FACT_ID),
        _allowed(),
    )

    assert hash_result.textual_facts_reproducible == 0.0
    assert hash_result.grounded_fact_integrity is False
    assert display_result.textual_fact_display_match == 0.0
    assert display_result.grounded_fact_integrity is False


def test_textual_integrity_counts_invalid_operation() -> None:
    result = _assess(
        _final(_fact(operation="unknown")),
        _plan(FACT_ID),
        _allowed(),
    )

    assert result.invalid_textual_operation_count == 1
    assert result.grounded_fact_integrity is False


def test_textual_integrity_without_text_is_explicitly_not_applicable() -> None:
    result = assess_textual_integrity(
        {"textual_facts": [], "narrative": "Total de registros: 25."},
        {
            "schema_version": "grounded-synthesis-plan-v1",
            "segments": [],
            "closing": "sin_cierre",
        },
        [],
    )

    assert result.applicable is False
    assert result.textual_fact_reference_coverage is None
    assert result.textual_facts_reproducible is None
    assert result.textual_fact_display_match is None
    assert result.orphan_factual_segments_count == 0
    assert result.invalid_textual_operation_count == 0
    assert result.grounded_fact_integrity is True


def test_textual_integrity_in_mixed_answer_does_not_change_quantitative_claims() -> None:
    final = _final(_fact())
    final["claims"] = [
        {
            "claim_id": "66666666-6666-4666-8666-666666666666",
            "display_value": "25",
            "source_hash": f"sha256:{'c' * 64}",
        }
    ]
    original_claims = deepcopy(final["claims"])

    result = _assess(final, _plan(FACT_ID), _allowed())

    assert result.grounded_fact_integrity is True
    assert final["claims"] == original_claims


def test_textual_integrity_is_deterministic_for_equivalent_inputs() -> None:
    first = _assess(_final(_fact()), _plan(FACT_ID), _allowed())
    second = _assess(_final(_fact()), _plan(FACT_ID), _allowed())

    assert first == second


def test_textual_plan_with_empty_public_list_is_applicable_and_fails() -> None:
    result = assess_textual_integrity(
        _final(narrative="La categoría seleccionada es Salud."),
        _plan(FACT_ID),
        _allowed(),
        [_fact()],
    )

    assert result.applicable is True
    assert result.textual_fact_reference_coverage == 0.0
    assert result.textual_facts_reproducible == 0.0
    assert result.textual_fact_display_match == 1.0
    assert result.grounded_fact_integrity is False


def test_allowed_textual_fact_with_empty_public_list_is_applicable_and_fails() -> None:
    result = assess_textual_integrity(
        _final(narrative=""),
        None,
        _allowed(),
        [_fact()],
    )

    assert result.applicable is True
    assert result.textual_facts_reproducible == 0.0
    assert result.textual_fact_display_match == 0.0
    assert result.grounded_fact_integrity is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("operation", "value_presence"),
        ("fact", "La categoría seleccionada es Educación."),
        ("display_value", "Educación"),
        ("evidence_id", "77777777-7777-4777-8777-777777777777"),
        ("dataset_id", "wxyz-9876"),
        ("source_row_indexes", [1]),
        ("columns", ["otra_columna"]),
        ("normalization_profile", "text-es-v2"),
        ("algorithm_version", "textual-fact-v2"),
        ("operation_params", {"target_value": "Salud"}),
        ("source_hash", f"sha256-jcs-v1:{'b' * 64}"),
    ],
)
def test_each_public_material_change_breaks_reproducibility(
    field: str,
    replacement: object,
) -> None:
    changed = deepcopy(_fact())
    changed[field] = replacement

    result = _assess(_final(changed), _plan(FACT_ID), _allowed())

    assert result.textual_facts_reproducible == 0.0
    assert result.grounded_fact_integrity is False


@pytest.mark.parametrize(
    ("final", "plan", "allowed"),
    [
        (_final(_fact()), _plan(FACT_ID), []),
        (
            {**_final(_fact()), "run_id": None},
            _plan(FACT_ID),
            [],
        ),
        (
            _final(_fact()),
            _plan(FACT_ID),
            [{"fact_kind": "textual", "id": "no-es-uuid"}],
        ),
        (_final(_fact()), {"segments": "inválido"}, _allowed()),
        (
            _final(_fact()),
            _plan("88888888-8888-4888-8888-888888888888"),
            _allowed(),
        ),
    ],
)
def test_invalid_structured_inputs_become_failed_metrics(
    final: dict,
    plan: dict,
    allowed: list[dict],
) -> None:
    result = assess_textual_integrity(final, plan, allowed, [_fact()])

    assert result.applicable is True
    assert result.grounded_fact_integrity is False
