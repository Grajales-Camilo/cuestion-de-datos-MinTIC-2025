from datetime import UTC, datetime

from app.catalog.coverage import (
    AmbiguousAliasGroup,
    UnresolvedCandidate,
    build_coverage_report,
)

_GENERATED_AT = datetime(2026, 7, 8, tzinfo=UTC)


def test_coverage_at_or_above_target_has_no_gap() -> None:
    report = build_coverage_report(
        counts_by_status={"verified": 90, "unknown": 10},
        total_datasets=100,
        total_active_datasets=100,
        ambiguous_aliases=[],
        unresolved_candidates=[],
        generated_at=_GENERATED_AT,
    )

    assert report.verified_ratio_active == 0.9
    assert report.coverage_gap is False
    assert report.to_dict()["gap_explanation"] is None


def test_coverage_below_target_reports_explicit_gap() -> None:
    report = build_coverage_report(
        counts_by_status={"verified": 163, "unknown": 8252},
        total_datasets=8415,
        total_active_datasets=8415,
        ambiguous_aliases=[],
        unresolved_candidates=[],
        generated_at=_GENERATED_AT,
    )

    assert report.coverage_gap is True
    payload = report.to_dict()
    assert payload["gap_explanation"] is not None
    assert "90%" in payload["gap_explanation"]


def test_coverage_with_zero_active_datasets_does_not_divide_by_zero() -> None:
    report = build_coverage_report(
        counts_by_status={},
        total_datasets=0,
        total_active_datasets=0,
        ambiguous_aliases=[],
        unresolved_candidates=[],
        generated_at=_GENERATED_AT,
    )

    assert report.verified_ratio_active == 0.0
    assert report.coverage_gap is True


def test_to_dict_serializes_ambiguous_aliases_and_candidates() -> None:
    report = build_coverage_report(
        counts_by_status={"verified": 1, "unknown": 1},
        total_datasets=2,
        total_active_datasets=2,
        ambiguous_aliases=[
            AmbiguousAliasGroup(
                alias_normalized="SECRETARIA DE EDUCACION",
                publisher_ids=["alcaldia-bogota", "alcaldia-medellin"],
            )
        ],
        unresolved_candidates=[
            UnresolvedCandidate(
                publisher_text="Alcaldia de Cali",
                dataset_count=42,
                sample_dataset_ids=["abcd-1234"],
            )
        ],
        generated_at=_GENERATED_AT,
    )

    payload = report.to_dict()
    assert payload["ambiguous_aliases"] == [
        {
            "alias_normalized": "SECRETARIA DE EDUCACION",
            "publisher_ids": ["alcaldia-bogota", "alcaldia-medellin"],
        }
    ]
    assert payload["unresolved_publisher_candidates"] == [
        {
            "publisher_text": "Alcaldia de Cali",
            "dataset_count": 42,
            "sample_dataset_ids": ["abcd-1234"],
        }
    ]
    assert payload["generated_at"] == "2026-07-08T00:00:00+00:00"


def test_custom_coverage_target_is_respected() -> None:
    report = build_coverage_report(
        counts_by_status={"verified": 50, "unknown": 50},
        total_datasets=100,
        total_active_datasets=100,
        ambiguous_aliases=[],
        unresolved_candidates=[],
        generated_at=_GENERATED_AT,
        coverage_target=0.5,
    )

    assert report.coverage_gap is False
