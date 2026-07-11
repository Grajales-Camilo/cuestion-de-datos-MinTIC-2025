from __future__ import annotations

from eval.loader import GoldenCase
from eval.metrics import assess_case, recall_hit_at_10


def _positive_case(expected_facts=()) -> GoldenCase:
    return GoldenCase("p", "positive", "q", ("abcd-1234",), expected_facts, 1, "n")


def test_positive_requires_completed_answer_with_expected_dataset() -> None:
    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"municipio": "Zona Bananera", "tasa": "2.44"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.passed is True
    assert result.expected_dataset_hit is True
    assert result.facts_verified is True


def test_positive_fails_when_expected_facts_do_not_match_tolerance() -> None:
    """Acertar el dataset no basta: la cifra real debe coincidir con expected_value."""

    case = _positive_case(
        expected_facts=(
            {
                "description": "x",
                "expected_value": {"municipio": "Zona Bananera", "tasa": "2.44"},
                "tolerance": 0.001,
            },
        ),
    )
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [
                {
                    "dataset_id": "abcd-1234",
                    "rows": [{"municipio": "Zona Bananera", "tasa": "9.99"}],
                }
            ],
            "claims": [],
        },
    )

    assert result.expected_dataset_hit is True
    assert result.facts_verified is False
    assert result.passed is False


def test_negative_fails_when_it_returns_evidence() -> None:
    case = GoldenCase("n", "negative", "q", (), (), 2, "n")
    result = assess_case(
        case,
        {"status": "no_evidence", "evidence": [{"dataset_id": "abcd-1234"}], "claims": []},
    )

    assert result.passed is False
    assert result.fabrication is True
    assert result.recall_hit is None


def test_collect_orphan_figures_are_reported_on_the_assessment() -> None:
    case = _positive_case()
    result = assess_case(
        case,
        {
            "status": "completed",
            "evidence": [{"dataset_id": "abcd-1234", "rows": []}],
            "claims": [{"display_value": "10", "evidence_id": "e1"}],
            "summary": "La tasa fue del 87%, muy por encima del 10 esperado.",
        },
    )

    assert "87" in "".join(result.orphan_figures)


def test_recall_hit_at_10_true_when_expected_dataset_in_search_results() -> None:
    case = _positive_case()
    assert recall_hit_at_10(case, ["other-id", "abcd-1234"]) is True
    assert recall_hit_at_10(case, ["other-id"]) is False


def test_recall_hit_at_10_is_none_for_negative_cases() -> None:
    case = GoldenCase("n", "negative", "q", (), (), 2, "n")
    assert recall_hit_at_10(case, ["abcd-1234"]) is None
