from datetime import UTC, datetime

from app.quality.cutoff import infer_data_cutoff

EVALUATED_AT = datetime(2026, 7, 9, tzinfo=UTC)


def test_infers_cutoff_from_year_column_as_end_of_year() -> None:
    rows = [{"a_o": "2023"}, {"a_o": "2025"}, {"a_o": "2024"}]

    result = infer_data_cutoff(rows, EVALUATED_AT)

    assert result is not None
    assert result.data_cutoff_at == datetime(2025, 12, 31, tzinfo=UTC)
    assert result.column == "a_o"
    assert result.method == "max_temporal_column"


def test_prefers_strong_keyword_column_with_higher_confidence() -> None:
    rows = [
        {"a_o": "2020", "fecha_corte": "2025-03-15"},
        {"a_o": "2021", "fecha_corte": "2025-01-01"},
    ]

    result = infer_data_cutoff(rows, EVALUATED_AT)

    assert result is not None
    assert result.column == "fecha_corte"
    assert result.confidence == 0.9
    assert result.data_cutoff_at == datetime(2025, 3, 15, tzinfo=UTC)


def test_returns_none_without_any_temporal_column() -> None:
    rows = [{"nombre": "Juan"}, {"nombre": "Ana"}]

    assert infer_data_cutoff(rows, EVALUATED_AT) is None


def test_returns_none_with_empty_rows() -> None:
    assert infer_data_cutoff([], EVALUATED_AT) is None


def test_discards_column_that_fails_to_parse_in_any_row() -> None:
    rows = [{"a_o": "2025"}, {"a_o": "no es un año"}]

    assert infer_data_cutoff(rows, EVALUATED_AT) is None


def test_parses_full_iso_datetime() -> None:
    rows = [{"fecha_final": "2025-12-31T00:00:00.000"}]

    result = infer_data_cutoff(rows, EVALUATED_AT)

    assert result is not None
    assert result.data_cutoff_at == datetime(2025, 12, 31, tzinfo=UTC)
