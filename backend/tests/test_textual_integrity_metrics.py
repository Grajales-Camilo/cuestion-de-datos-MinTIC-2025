from __future__ import annotations

from copy import deepcopy

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


def test_textual_integrity_complete_is_reproducible_and_privacy_safe() -> None:
    result = assess_textual_integrity(_final(_fact()), _plan(FACT_ID), _allowed())

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
    result = assess_textual_integrity(
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
    hash_result = assess_textual_integrity(_final(changed), _plan(FACT_ID), _allowed())
    display_result = assess_textual_integrity(
        _final(_fact(), narrative="La categoría seleccionada es salud."),
        _plan(FACT_ID),
        _allowed(),
    )

    assert hash_result.textual_facts_reproducible == 0.0
    assert hash_result.grounded_fact_integrity is False
    assert display_result.textual_fact_display_match == 0.0
    assert display_result.grounded_fact_integrity is False


def test_textual_integrity_counts_invalid_operation() -> None:
    result = assess_textual_integrity(
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

    result = assess_textual_integrity(final, _plan(FACT_ID), _allowed())

    assert result.grounded_fact_integrity is True
    assert final["claims"] == original_claims


def test_textual_integrity_is_deterministic_for_equivalent_inputs() -> None:
    first = assess_textual_integrity(_final(_fact()), _plan(FACT_ID), _allowed())
    second = assess_textual_integrity(_final(_fact()), _plan(FACT_ID), _allowed())

    assert first == second
