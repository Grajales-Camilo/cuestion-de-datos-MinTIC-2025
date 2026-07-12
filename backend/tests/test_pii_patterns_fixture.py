import re

from app.quality.pii_classifier import load_pii_patterns


def test_fixture_loads() -> None:
    fixture = load_pii_patterns()

    assert fixture.default_column_risk == "unknown"
    assert len(fixture.high_risk_column_patterns) > 0
    assert len(fixture.low_risk_column_allowlist) > 0


def test_every_pattern_has_valid_regex_and_reason() -> None:
    fixture = load_pii_patterns()

    all_patterns = (
        fixture.high_risk_column_patterns
        + fixture.medium_risk_column_patterns
        + fixture.low_risk_column_allowlist
    )
    for pattern in all_patterns:
        re.compile(pattern.pattern)
        assert pattern.reason


def test_dataset_level_keywords_are_valid_regex() -> None:
    fixture = load_pii_patterns()

    for keywords in fixture.dataset_level_keywords.values():
        for keyword in keywords:
            re.compile(keyword)


def test_pattern_ids_are_unique_within_each_list() -> None:
    fixture = load_pii_patterns()

    for patterns in (
        fixture.high_risk_column_patterns,
        fixture.medium_risk_column_patterns,
        fixture.low_risk_column_allowlist,
    ):
        ids = [pattern.id for pattern in patterns]
        assert len(ids) == len(set(ids))


def test_reviewed_dataset_columns_have_provenance_and_no_duplicates() -> None:
    fixture = load_pii_patterns()

    assert len(fixture.reviewed_dataset_columns) == 37
    for dataset_id, review in fixture.reviewed_dataset_columns.items():
        assert re.fullmatch(r"[a-z0-9]{4}-[a-z0-9]{4}", dataset_id)
        assert review.risk_level in {"low", "medium", "high"}
        assert review.columns
        assert review.source.startswith("https://")
        assert review.reason
