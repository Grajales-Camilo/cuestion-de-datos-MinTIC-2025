from __future__ import annotations

from eval.loader import GoldenCase
from eval.persistence import case_signature


def test_case_signature_is_stable_for_equivalent_case() -> None:
    case = GoldenCase(
        case_id="case-1",
        case_type="positive",
        question="Pregunta",
        expected_dataset_ids=("abcd-1234",),
        expected_facts=({"expected_value": {"total": "10"}},),
        seed=601001,
        notes="Nota",
    )

    assert case_signature(case) == case_signature(case)


def test_case_signature_changes_when_frozen_content_changes() -> None:
    original = GoldenCase("case-1", "negative", "Pregunta", (), (), 601001, "Nota")
    changed = GoldenCase("case-1", "negative", "Otra pregunta", (), (), 601001, "Nota")

    assert case_signature(original) != case_signature(changed)
